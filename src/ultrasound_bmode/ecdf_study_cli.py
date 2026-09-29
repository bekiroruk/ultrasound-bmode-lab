"""Audit a bin-free, single-threshold gCNR candidate and IID DKW bounds."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .accelerated import numba_plane_wave_delay_and_sum
from .coverage_cli import rayleigh_truth, wilson_interval
from .metrics import _generalized_cnr, circular_mask
from .rayleigh_coverage_cli import _draw_field
from .real_data import load_picmus_uff
from .reconstruction_quality_cli import _sha256
from .spatial_roi import _positive_integer

SOURCE = "https://doi.org/10.1109/TUFFC.2023.3289157"
SCENARIOS = ("iid_rayleigh", "offset_correlated_rayleigh", "iid_lognormal_stress")


def ecdf_threshold_separation(target, background):
    """Range of the two eCDF difference (not general multimodal density overlap).

    Equals population gCNR only if the population density difference changes sign
    once. Ties are evaluated after all samples at the same amplitude enter each eCDF.
    """
    target = np.asarray(target, dtype=float)
    background = np.asarray(background, dtype=float)
    if (target.ndim != 1 or background.ndim != 1 or not target.size or not background.size
            or not np.isfinite(target).all() or not np.isfinite(background).all()):
        raise ValueError("expected two nonempty finite one-dimensional samples")
    target_sorted = np.sort(target)
    background_sorted = np.sort(background)
    support = np.union1d(target_sorted, background_sorted)
    difference = (np.searchsorted(target_sorted, support, side="right") / target.size
                  - np.searchsorted(background_sorted, support, side="right")
                  / background.size)
    return float(np.max(difference) - np.min(difference))


def dkw_interval(estimate, target_count, background_count, alpha=0.05):
    """Conservative simultaneous-CDF bound for independent samples in each ROI.

    DKW per group with alpha/2 allocation gives |Hhat-H| <= eps_t+eps_b.
    The range functional is 2-Lipschitz in the sup norm. Independence between
    the two groups is not needed, but independence within each group is essential.
    """
    if not np.isfinite(estimate) or not 0 <= estimate <= 1:
        raise ValueError("estimate must be in [0, 1]")
    _positive_integer(target_count, "target_count")
    _positive_integer(background_count, "background_count")
    if not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    epsilon = (math.sqrt(math.log(4/alpha)/(2*target_count))
               + math.sqrt(math.log(4/alpha)/(2*background_count)))
    radius = 2*epsilon
    return [max(0.0, estimate-radius), min(1.0, estimate+radius)]


def roi_samples(field, axis, roi, *, tile_side=1, tile_origin=0):
    """Fixed target disk/background annulus; optionally one value per source cell."""
    target = circular_mask(axis, axis, roi.center_x_m, roi.center_z_m, roi.radius_m)
    background = circular_mask(axis, axis, roi.center_x_m, roi.center_z_m,
                               roi.radius_m+3e-3)
    background &= ~circular_mask(axis, axis, roi.center_x_m, roi.center_z_m,
                                 roi.radius_m+1e-3)
    if tile_side == 1:
        return field[target], field[background]
    samples = []
    for mask in (target, background):
        rows, columns = np.nonzero(mask)
        cells = np.column_stack(((rows-tile_origin)//tile_side,
                                 (columns-tile_origin)//tile_side))
        _, first = np.unique(cells, axis=0, return_index=True)
        samples.append(field[rows[first], columns[first]])
    return tuple(samples)


def summarize(records, truth):
    summary = []
    for scenario in SCENARIOS:
        for sampling in (("pixels", "source_cells") if scenario == SCENARIOS[1]
                         else ("pixels",)):
            rows = [row for row in records if row["scenario"] == scenario
                    and row["sampling"] == sampling]
            covered = sum(lo <= truth[scenario] <= hi for row in rows
                          for lo, hi in [row["dkw95"]])
            summary.append({
                "scenario": scenario, "sampling": sampling, "trials": len(rows),
                "covered": covered, "coverage": covered/len(rows),
                "coverage_wilson95": wilson_interval(covered, len(rows)),
                "ecdf_bias": float(np.mean([r["ecdf"] for r in rows])-truth[scenario]),
                "histogram_bias": float(np.mean([r["histogram64"] for r in rows])
                                        - truth[scenario]),
                "dkw_mean_width": float(np.mean([r["dkw95"][1]-r["dkw95"][0]
                                                  for r in rows])),
                "dkw_nontrivial_fraction": float(np.mean(
                    [r["dkw95"][0] > 0 or r["dkw95"][1] < 1 for r in rows])),
                "mean_target_count": float(np.mean([r["target_count"] for r in rows])),
                "mean_background_count": float(np.mean([r["background_count"] for r in rows])),
            })
    return summary


def measured_phantom(path):
    """Descriptive threshold metric on real scanner RF and embedded UFF reference."""
    acquisition = load_picmus_uff(path)
    result = numba_plane_wave_delay_and_sum(
        acquisition, angle_count=11, f_number=1.7, analytic=True,
        angle_batch_size=8, axial_stride=2, lateral_stride=2,
    )
    x, z = result.x_axis_m, result.z_axis_m
    np.testing.assert_array_equal(x, acquisition.x_axis_m[::2])
    np.testing.assert_array_equal(z, acquisition.z_axis_m[::2])
    images = {"analytic_11_angles": np.abs(result.rf),
              "embedded_uff_reference": np.abs(acquisition.reference_iq)[::2, ::2]}
    records = []
    for name, image in images.items():
        for depth_mm in (15, 43):
            target = circular_mask(x, z, 0, depth_mm*1e-3, 1.5e-3)
            background = circular_mask(x, z, 0, depth_mm*1e-3, 4.5e-3)
            background &= ~circular_mask(x, z, 0, depth_mm*1e-3, 2.5e-3)
            a, b = image[target], image[background]
            records.append({
                "image": name, "cyst_depth_mm": depth_mm,
                "target_pixels": int(a.size), "background_pixels": int(b.size),
                "ecdf_threshold_separation": ecdf_threshold_separation(a, b),
                "histogram64_gcnr": _generalized_cnr(a, b),
            })
    return {
        "file": path.name, "sha256": _sha256(path), "citation": acquisition.citation,
        "settings": {"angles": 11, "angle_indices": result.angle_indices.tolist(),
                     "f_number": 1.7, "analytic": True, "angle_batch_size": 8,
                     "axial_stride": 2, "lateral_stride": 2},
        "roi_mm": {"centers": [[0, 15], [0, 43]], "target_radius": 1.5,
                   "background_inner_radius": 2.5, "background_outer_radius": 4.5},
        "records": records,
        "limitation": ("Single physical phantom acquisition; no known population gCNR, "
                       "sampling independence, or one-crossing verification. No DKW "
                       "confidence interval or accuracy claim is made for these images."),
    }


def run_study(output_dir, *, trials=200, seed=20261005, phantom_path=None):
    _positive_integer(trials, "trials", 2)
    _positive_integer(seed, "seed", 0)
    truth = {"iid_rayleigh": rayleigh_truth()["generalized_cnr"],
             "offset_correlated_rayleigh": rayleigh_truth()["generalized_cnr"],
             "iid_lognormal_stress": math.erf(math.log(2)/(2*math.sqrt(2)*0.7))}
    report = {
        "study": "Bin-free single-threshold eCDF and conservative IID DKW audit",
        "source": SOURCE,
        "settings": {"trials_per_scenario": trials, "seed": seed, "alpha": 0.05,
                     "source_cell_side": 4, "source_cell_origin": [2, 2],
                     "histogram_bins": 64},
        "truth": truth, "records": [],
        "scope": ("Independently generated synthetic envelope fields, not RF. Rayleigh and "
                  "same-shape lognormal pairs each have one population density crossing, "
                  "so population eCDF range equals gCNR. Same fixed circular ROIs as the "
                  "previous coverage audit. The correlated generator repeats independent "
                  "Rayleigh source cells in offset 4x4 tiles. One value per occupied source "
                  "cell is an oracle diagnostic, not an estimated decorrelation method."),
        "limitations": ("DKW coverage is distribution-free for independent samples within "
                        "each region, not for correlated image pixels. The source-cell "
                        "diagnostic knows the synthetic generator; measured images do not. "
                        "The eCDF range can understate general multimodal density-overlap "
                        "gCNR. No clinical or measured-image 95% interval claim."),
    }
    streams = np.random.SeedSequence(seed).spawn(len(SCENARIOS)*trials)
    for case_index, scenario in enumerate(SCENARIOS):
        for trial in range(trials):
            field, axis, roi = _draw_field(
                np.random.default_rng(streams[case_index*trials+trial]), scenario)
            for sampling in (("pixels", "source_cells") if case_index == 1
                             else ("pixels",)):
                side, origin = (4, 2) if sampling == "source_cells" else (1, 0)
                target, background = roi_samples(field, axis, roi, tile_side=side,
                                                 tile_origin=origin)
                estimate = ecdf_threshold_separation(target, background)
                report["records"].append({
                    "scenario": scenario, "trial": trial, "sampling": sampling,
                    "target_count": int(target.size), "background_count": int(background.size),
                    "ecdf": estimate, "histogram64": _generalized_cnr(target, background),
                    "dkw95": dkw_interval(estimate, target.size, background.size),
                })
        print(f"{scenario}: {trials} independent fields", flush=True)
    report["summaries"] = summarize(report["records"], truth)
    if phantom_path is not None:
        report["measured_phantom"] = measured_phantom(phantom_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n",
                                             encoding="utf-8")
    lines = ["# Bin-free threshold separation: coverage and measured-phantom audit", "",
             report["scope"], "", report["limitations"], "",
             f"{trials} independent fields per scenario; 95% DKW simultaneous-CDF bounds.",
             f"Method: [Schlunk & Byram (2023)]({SOURCE}).", "",
             "| Scenario | Sampling | eCDF bias | 64-bin bias | DKW coverage | Mean width |",
             "|---|---|---:|---:|---:|---:|"]
    for row in report["summaries"]:
        lines.append(f"| {row['scenario']} | {row['sampling']} | {row['ecdf_bias']:+.4f} | "
                     f"{row['histogram_bias']:+.4f} | {row['coverage']:.3f} | "
                     f"{row['dkw_mean_width']:.3f} |")
    if "measured_phantom" in report:
        lines += ["", "## Physical phantom, measured device RF", "",
                  ("Point estimates only; the eCDF column is threshold separation, not "
                   "a validated general gCNR or a calibrated interval."), "",
                  "| Image | Cyst depth | eCDF threshold | 64-bin gCNR |",
                  "|---|---:|---:|---:|"]
        for row in report["measured_phantom"]["records"]:
            lines.append(f"| {row['image']} | {row['cyst_depth_mm']} mm | "
                         f"{row['ecdf_threshold_separation']:.3f} | "
                         f"{row['histogram64_gcnr']:.3f} |")
    lines += ["", "![Synthetic audit](comparison.png)", "", "[Raw records](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    summary = report["summaries"]
    positions = np.arange(len(summary))
    labels = ["IID Rayleigh\npixels", "4×4 Rayleigh\npixels",
              "4×4 Rayleigh\nsource cells", "IID lognormal\npixels"]
    axes[0].bar(positions-0.18, [r["ecdf_bias"] for r in summary], width=0.36,
                label="eCDF threshold")
    axes[0].bar(positions+0.18, [r["histogram_bias"] for r in summary], width=0.36,
                label="64-bin histogram")
    axes[0].axhline(0, color="black", linewidth=0.7)
    axes[0].set(ylabel="Mean estimate − population gCNR", title="Point-estimate bias")
    axes[0].legend(fontsize=8)
    axes[1].bar(positions, [r["dkw_mean_width"] for r in summary], color="#417e9c")
    axes[1].set(ylabel="Mean DKW interval width", ylim=(0, 1.05),
                title="Conservative interval informativeness")
    for ax in axes:
        ax.set_xticks(positions, labels)
        ax.tick_params(axis="x", labelsize=7)
    fig.savefig(output_dir / "comparison.png", dpi=160)
    plt.close(fig)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/ecdf_study"))
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--phantom-path", type=Path, default=None)
    args = parser.parse_args()
    run_study(args.output_dir, trials=args.trials, seed=args.seed, phantom_path=args.phantom_path)


if __name__ == "__main__":
    main()
