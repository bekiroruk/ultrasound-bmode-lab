"""Exploratory eCDF topology and directional texture on measured RF acquisitions."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle

from .accelerated import numba_plane_wave_delay_and_sum
from .ecdf_study_cli import ecdf_threshold_separation
from .external_validation_cli import _cases, _load
from .metrics import _generalized_cnr, circular_mask
from .real_data import load_picmus_uff, reference_bmode
from .reconstruction_quality_cli import _sha256
from .roi import LumenRoi, locate_carotid_lumen

CASES = ("picmus_cross", "epfl_v5", "epfl_v8")
BINS = (16, 32, 64)
MAX_LAG = 16
CONTROL_REPEATS = 100
CONTROL_SEED = 20261006


def rank_binned_diagnostic(target, background, bins):
    """Pooled-rank equal-count histogram TV and density-difference sign changes.

    This is a resolution-sensitive topology *diagnostic*, not an estimator of
    population crossing count. Tied amplitudes always enter the same bin.
    """
    if isinstance(bins, bool) or not isinstance(bins, int) or bins < 2:
        raise ValueError("bins must be an integer >= 2")
    target, background = np.asarray(target, dtype=float), np.asarray(background, dtype=float)
    if (target.ndim != 1 or background.ndim != 1 or not target.size or not background.size
            or not np.isfinite(target).all() or not np.isfinite(background).all()):
        raise ValueError("expected two nonempty finite one-dimensional samples")
    pooled = np.concatenate((target, background))
    _, inverse, counts = np.unique(pooled, return_inverse=True, return_counts=True)
    midpoint = np.cumsum(counts) - counts/2
    rank_bins = np.minimum((midpoint*bins/pooled.size).astype(int), bins-1)[inverse]
    a = np.bincount(rank_bins[:target.size], minlength=bins)/target.size
    b = np.bincount(rank_bins[target.size:], minlength=bins)/background.size
    difference = a-b
    nonzero = np.sign(difference[difference != 0])
    return {
        "bins": bins,
        "rank_binned_tv": float(np.sum(np.abs(difference))/2),
        "sign_changes": int(np.count_nonzero(np.diff(nonzero))) if nonzero.size else 0,
        "empty_bins": int(np.count_nonzero(a+b == 0)),
    }


def single_crossing_resolution_control(target_count, background_count, *, repeats, seed):
    """Sample-count-matched IID Rayleigh example with exactly one density crossing."""
    for value in (target_count, background_count, repeats):
        if isinstance(value, bool) or not isinstance(value, int) or value < 2:
            raise ValueError("counts and repeats must be integers >= 2")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    rng = np.random.default_rng(seed)
    changes = {bins: [] for bins in BINS}
    for _ in range(repeats):
        target = rng.rayleigh(scale=0.5, size=target_count)
        background = rng.rayleigh(scale=1.0, size=background_count)
        for bins in BINS:
            changes[bins].append(rank_binned_diagnostic(target, background, bins)
                                 ["sign_changes"])
    return {str(bins): {"median": float(np.median(changes[bins])),
                        "p05_p95": np.percentile(changes[bins], [5, 95]).tolist()}
            for bins in BINS}


def directional_autocorrelation(image, mask, *, max_lag=MAX_LAG, min_pairs=30):
    """Centered log-envelope correlation for pairs entirely inside one fixed ROI."""
    values = np.asarray(image, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if (values.ndim != 2 or values.shape != mask.shape or not np.isfinite(values).all()
            or np.any(values < 0) or mask.sum() < min_pairs
            or isinstance(max_lag, bool) or not isinstance(max_lag, int) or max_lag < 1):
        raise ValueError("invalid image, mask or lag")
    scale = float(np.median(values[mask]))
    if scale <= 0:
        raise ValueError("ROI median envelope must be positive")
    transformed = np.log1p(values/scale)
    variance = float(np.var(transformed[mask]))
    if variance <= 0:
        raise ValueError("ROI texture variance must be positive")
    output = {}
    for name, direction in (("axial", 0), ("lateral", 1)):
        correlations = [1.0]
        pairs = [int(mask.sum())]
        for lag in range(1, max_lag+1):
            if lag >= values.shape[direction]:
                correlations.append(None)
                pairs.append(0)
                continue
            if direction == 0:
                valid = mask[:-lag, :] & mask[lag:, :]
                first, second = transformed[:-lag, :], transformed[lag:, :]
            else:
                valid = mask[:, :-lag] & mask[:, lag:]
                first, second = transformed[:, :-lag], transformed[:, lag:]
            pair_count = int(np.sum(valid))
            pairs.append(pair_count)
            if pair_count < min_pairs:
                correlations.append(None)
                continue
            a, b = first[valid], second[valid]
            denominator = float(np.std(a)*np.std(b))
            correlations.append(float(np.mean((a-np.mean(a))*(b-np.mean(b)))
                                      / denominator) if denominator > 0 else None)
        crossing = None
        threshold = 1/math.e
        for lag in range(1, len(correlations)):
            current = correlations[lag]
            previous = correlations[lag-1]
            if current is None or previous is None:
                break
            if current <= threshold < previous:
                crossing = float(lag-1 + (previous-threshold)/(previous-current))
                break
        output[name] = {"rho": correlations, "pair_counts": pairs,
                        "one_over_e_crossing_pixels": crossing}
    return output


def _masks(x, z, roi, *, background_inner_offset, background_outer_offset):
    target = circular_mask(x, z, roi.center_x_m, roi.center_z_m, roi.radius_m)
    inner = circular_mask(x, z, roi.center_x_m, roi.center_z_m,
                          roi.radius_m+background_inner_offset)
    outer = circular_mask(x, z, roi.center_x_m, roi.center_z_m,
                          roi.radius_m+background_outer_offset)
    background = outer & ~inner
    if min(int(target.sum()), int(background.sum())) < 50:
        raise ValueError("fixed ROI has fewer than 50 pixels in one region")
    return target, background


def evaluate_region(envelope, x, z, roi, *, inner_offset, outer_offset):
    target_mask, background_mask = _masks(
        x, z, roi, background_inner_offset=inner_offset,
        background_outer_offset=outer_offset)
    target, background = envelope[target_mask], envelope[background_mask]
    threshold = ecdf_threshold_separation(target, background)
    rank = [rank_binned_diagnostic(target, background, n) for n in BINS]
    texture = directional_autocorrelation(envelope, background_mask)
    for direction, spacing in (("axial", float(np.mean(np.diff(z)))),
                               ("lateral", float(np.mean(np.diff(x))))):
        pixels = texture[direction]["one_over_e_crossing_pixels"]
        texture[direction]["one_over_e_crossing_mm"] = (
            None if pixels is None else pixels*spacing*1e3)
    return {
        "roi_m": asdict(roi), "background_inner_radius_m": roi.radius_m+inner_offset,
        "background_outer_radius_m": roi.radius_m+outer_offset,
        "target_pixels": int(target.size), "background_pixels": int(background.size),
        "ecdf_threshold_separation": threshold,
        "histogram64_gcnr": _generalized_cnr(target, background),
        "rank_binned": rank, "background_texture": texture,
    }


def _reconstruct(acquisition, count):
    result = numba_plane_wave_delay_and_sum(
        acquisition, angle_count=count, f_number=1.7, analytic=True,
        angle_batch_size=8, axial_stride=2, lateral_stride=2,
    )
    np.testing.assert_array_equal(result.x_axis_m, acquisition.x_axis_m[::2])
    np.testing.assert_array_equal(result.z_axis_m, acquisition.z_axis_m[::2])
    return result


def run_transfer(data_dir: Path, output_dir: Path):
    cases = [case for case in _cases(data_dir) if case.identifier in CASES]
    phantom_path = data_dir / "PICMUS_experiment_contrast_speckle.uff"
    required = [case.path for case in cases] + [phantom_path]
    required += [data_dir / "epfl/settings" / name for name in
                 ("beamforming_settings.yaml", "steering_angles.npy", "time_axis.npy")]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing measured input: " + ", ".join(missing))
    report = {
        "study": "Measured-RF eCDF topology and directional texture diagnostic",
        "settings": {"human_case_ids": list(CASES), "human_angles": "all available",
                     "phantom_angles": 11, "f_number": 1.7, "analytic": True,
                     "angle_batch_size": 8, "axial_stride": 2, "lateral_stride": 2,
                     "rank_bin_counts": list(BINS), "max_lag_pixels": MAX_LAG,
                     "single_crossing_control_repeats": CONTROL_REPEATS,
                     "single_crossing_control_seed": CONTROL_SEED,
                     "minimum_autocorrelation_pairs": 30,
                     "autocorrelation_transform": "log1p(envelope/background median)"},
        "scope": ("Two explicitly distinct EPFL volunteers, a PICMUS cross-section with "
                  "unspecified subject identity, and one physical phantom acquisition. "
                  "Human ROI heuristic uses the embedded UFF reference for PICMUS and each "
                  "EPFL case's own full-angle image. Phantom cyst ROIs are fixed nominal "
                  "geometry. These are previously inspected acquisitions, not blinded "
                  "prospective validation."),
        "limitations": ("Raw rank-bin sign changes and total-variation gaps vary with bins, "
                        "finite samples and spatial dependence: they cannot verify a "
                        "population density crossing count. The sample-count-matched "
                        "Rayleigh control is IID and not a model fit or hypothesis test. "
                        "Annulus texture is not "
                        "homogeneous or stationary by assumption; 1/e decorrelation is "
                        "descriptive, not an independent-sample count or a bootstrap "
                        "block-size recommendation. No clinical or 95% coverage claim."),
        "datasets": [], "regions": [],
    }
    panels = []
    for case in cases:
        acquisition = _load(case, data_dir)
        count = int(acquisition.transmit_angles_rad.size)
        result = _reconstruct(acquisition, count)
        x, z = result.x_axis_m, result.z_axis_m
        image = np.abs(result.rf)
        if case.identifier == "picmus_cross":
            roi = locate_carotid_lumen(reference_bmode(acquisition)[::2, ::2], x, z)
            selection = "embedded UFF reference heuristic"
        else:
            roi = locate_carotid_lumen(result.bmode_db, x, z)
            selection = "same-acquisition full-angle image heuristic; selection bias"
        region = evaluate_region(image, x, z, roi, inner_offset=1e-3, outer_offset=3e-3)
        region.update(case=case.identifier, label=case.label, roi_selection=selection)
        report["regions"].append(region)
        metadata = {"case": case.identifier, "file": case.path.name,
                    "sha256": _sha256(case.path), "subject": case.subject,
                    "platform": case.platform, "probe": case.probe,
                    "citation": acquisition.citation,
                    "channel_shape": list(acquisition.channel_data.shape),
                    "angle_indices": result.angle_indices.tolist(),
                    "grid_shape": list(image.shape),
                    "grid_spacing_mm": [float(np.mean(np.diff(z))*1e3),
                                        float(np.mean(np.diff(x))*1e3)]}
        if case.loader == "epfl":
            metadata["settings_sha256"] = {
                name: _sha256(data_dir / "epfl/settings" / name)
                for name in ("beamforming_settings.yaml", "steering_angles.npy",
                             "time_axis.npy")}
        report["datasets"].append(metadata)
        panels.append((case.label, result.bmode_db, x, z, [region]))
        print(f"{case.identifier}: {count} angles, ROI and texture measured", flush=True)
    acquisition = load_picmus_uff(phantom_path)
    result = _reconstruct(acquisition, 11)
    x, z, image = result.x_axis_m, result.z_axis_m, np.abs(result.rf)
    phantom_regions = []
    for label, depth_mm in (("shallow_cyst", 15), ("deep_cyst", 43)):
        roi = LumenRoi(0, depth_mm*1e-3, 1.5e-3)
        region = evaluate_region(image, x, z, roi, inner_offset=1e-3, outer_offset=3e-3)
        region.update(case="picmus_contrast_phantom", label=label,
                      roi_selection="fixed nominal cyst geometry")
        report["regions"].append(region)
        phantom_regions.append(region)
    control_mask = circular_mask(x, z, 10e-3, 28e-3, 3e-3)
    control_texture = directional_autocorrelation(image, control_mask)
    for direction, spacing in (("axial", float(np.mean(np.diff(z)))),
                               ("lateral", float(np.mean(np.diff(x))))):
        pixels = control_texture[direction]["one_over_e_crossing_pixels"]
        control_texture[direction]["one_over_e_crossing_mm"] = (
            None if pixels is None else pixels*spacing*1e3)
    report["phantom_homogeneous_speckle_control"] = {
        "center_mm": [10, 28], "radius_mm": 3, "pixels": int(control_mask.sum()),
        "background_texture": control_texture,
    }
    report["datasets"].append({
        "case": "picmus_contrast_phantom", "file": phantom_path.name,
        "sha256": _sha256(phantom_path), "citation": acquisition.citation,
        "channel_shape": list(acquisition.channel_data.shape),
        "angle_indices": result.angle_indices.tolist(), "grid_shape": list(image.shape),
        "grid_spacing_mm": [float(np.mean(np.diff(z))*1e3),
                            float(np.mean(np.diff(x))*1e3)],
    })
    panels.append(("PICMUS physical phantom · 11 angles", result.bmode_db, x, z,
                   phantom_regions))
    for index, region in enumerate(report["regions"]):
        region["single_crossing_rayleigh_control"] = single_crossing_resolution_control(
            region["target_pixels"], region["background_pixels"],
            repeats=CONTROL_REPEATS, seed=CONTROL_SEED+index)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n",
                                             encoding="utf-8")
    _save_report(report, output_dir)
    _plot_rois(panels, output_dir / "rois.png")
    _plot_diagnostics(report["regions"], output_dir / "diagnostics.png")
    return report


def _save_report(report, output_dir):
    control = report["phantom_homogeneous_speckle_control"]["background_texture"]
    control_axial = control["axial"]["one_over_e_crossing_mm"]
    control_lateral = control["lateral"]["one_over_e_crossing_mm"]
    control_axial_text = "unresolved" if control_axial is None else f"{control_axial:.3f}"
    control_lateral_text = "unresolved" if control_lateral is None else f"{control_lateral:.3f}"
    lines = ["# Measured-RF eCDF and texture transfer diagnostic", "", report["scope"], "",
             report["limitations"], "",
             ("| Acquisition / ROI | eCDF threshold | 64-bin gCNR | Rank-TV 16/32/64 | "
              "Sign changes 16/32/64 | Axial 1/e mm | Lateral 1/e mm |"),
             "|---|---:|---:|---|---|---:|---:|"]
    for row in report["regions"]:
        rank = row["rank_binned"]
        axial = row["background_texture"]["axial"]["one_over_e_crossing_mm"]
        lateral = row["background_texture"]["lateral"]["one_over_e_crossing_mm"]
        lines.append(f"| {row['case']} / {row['label']} | "
                     f"{row['ecdf_threshold_separation']:.3f} | "
                     f"{row['histogram64_gcnr']:.3f} | "
                     + "/".join(f"{item['rank_binned_tv']:.3f}" for item in rank) + " | "
                     + "/".join(str(item["sign_changes"]) for item in rank) + " | "
                     + ("—" if axial is None else f"{axial:.3f}") + " | "
                     + ("—" if lateral is None else f"{lateral:.3f}") + " |")
    lines += ["", ("Sign changes are empirical bin-to-bin density-difference signs; they "
                   "are not a verified population crossing count. Rank-TV is an "
                   "equal-pooled-rank histogram diagnostic, not a replacement metric. "
                   "The directional 1/e values come from pair-centered Pearson "
                   "correlations of log-envelope pairs wholly inside the background "
                   "annulus; they are not independent sample spacings."), "",
              "## Finite-sample single-crossing control", "",
              ("For each ROI's pixel counts, 100 new IID Rayleigh pairs with scales "
               "0.5/1.0 and exactly one population density crossing were drawn. "
               "These are not fitted tissue models or p-values."), "",
              "| ROI | Observed 64-bin sign changes | IID one-crossing median [p05, p95] |",
              "|---|---:|---:|"]
    for row in report["regions"]:
        control = row["single_crossing_rayleigh_control"]["64"]
        observed = row["rank_binned"][-1]["sign_changes"]
        lo, hi = control["p05_p95"]
        lines.append(f"| {row['case']} / {row['label']} | {observed} | "
                     f"{control['median']:.0f} [{lo:.0f}, {hi:.0f}] |")
    lines += ["",
              ("The separate nominal homogeneous phantom speckle disk at x=10 mm, "
               "z=28 mm, radius=3 mm is a texture control. Its axial/lateral 1/e "
               f"lags are {control_axial_text}/{control_lateral_text} mm."), "",
              "![ROI overlays](rois.png)", "", "![Sensitivity plots](diagnostics.png)", "",
              "[Complete settings, provenance and autocorrelation curves](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _plot_rois(panels, path):
    fig, axes = plt.subplots(2, 2, figsize=(11, 10), layout="constrained")
    for axis, (label, bmode, x, z, regions) in zip(axes.ravel(), panels, strict=True):
        extent = (x[0]*1e3, x[-1]*1e3, z[-1]*1e3, z[0]*1e3)
        axis.imshow(bmode, cmap="gray", vmin=-60, vmax=0, extent=extent,
                    interpolation="nearest", aspect="equal")
        for region in regions:
            roi = region["roi_m"]
            for radius, color in ((roi["radius_m"], "#00e5ff"),
                                  (region["background_inner_radius_m"], "#ffcc00"),
                                  (region["background_outer_radius_m"], "#ffcc00")):
                axis.add_patch(Circle((roi["center_x_m"]*1e3, roi["center_z_m"]*1e3),
                                      radius*1e3, fill=False, color=color, lw=0.9))
        if "physical phantom" in label:
            axis.add_patch(Circle((10, 28), 3, fill=False, color="#e879f9",
                                  lw=1.2, linestyle="--"))
        axis.set(title=label, xlabel="Lateral [mm]", ylabel="Depth [mm]")
    fig.suptitle("Measured RF · cyan target, amber annulus, magenta phantom speckle control")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_diagnostics(regions, path):
    labels = ["PICMUS\ncarotid", "EPFL\n005", "EPFL\n008",
              "Phantom\n15 mm", "Phantom\n43 mm"]
    positions = np.arange(len(regions))
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), layout="constrained")
    axes[0].bar(positions-0.3, [r["ecdf_threshold_separation"] for r in regions],
                width=0.2, color="black", label="eCDF threshold")
    for offset, bins in zip((-0.1, 0.1, 0.3), BINS, strict=True):
        axes[0].bar(positions+offset,
                    [next(v["rank_binned_tv"] for v in r["rank_binned"]
                          if v["bins"] == bins) for r in regions],
                    width=0.2, label=f"Rank-TV {bins}")
    axes[0].set(ylabel="Separation estimate", ylim=(0, 1.05),
                title="Bin-resolution sensitivity")
    axes[0].legend(fontsize=8)
    for offset, direction in ((-0.18, "axial"), (0.18, "lateral")):
        axes[1].bar(positions+offset,
                    [r["background_texture"][direction]["one_over_e_crossing_mm"]
                     for r in regions], width=0.36, label=direction)
    axes[1].set(ylabel="1/e lag [mm]", title="Annulus log-envelope autocorrelation")
    axes[1].legend(fontsize=8)
    for axis in axes:
        axis.set_xticks(positions, labels)
        axis.tick_params(axis="x", labelsize=7)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/ecdf_transfer"))
    args = parser.parse_args()
    run_transfer(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
