"""Validate channel-analytic CPWC on measured phantoms and external acquisitions."""

from __future__ import annotations

import argparse
import json
import platform
from importlib.metadata import version
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle

from .accelerated import numba_plane_wave_delay_and_sum
from .external_validation_cli import _cases, _load
from .metrics import evaluate_similarity
from .phantom import (
    NOMINAL_POINT_TARGETS_M,
    measure_contrast_phantom,
    measure_resolution_phantom,
)
from .processing import envelope_detect, log_compress
from .real_data import load_picmus_uff
from .reconstruction_quality_cli import _sha256


def finite_json(value):
    """Represent unavailable numeric measurements with null, never invalid JSON NaN."""
    if isinstance(value, dict):
        return {key: finite_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def _envelope(result):
    return np.abs(result.rf) if np.iscomplexobj(result.rf) else envelope_detect(result.rf)


def grid_consistency(fine, coarse) -> dict:
    """Compare linear envelopes at identical coordinates without per-image renormalization."""
    np.testing.assert_array_equal(fine.x_axis_m[::2], coarse.x_axis_m)
    np.testing.assert_array_equal(fine.z_axis_m[::2], coarse.z_axis_m)
    shared = _envelope(fine)[::2, ::2]
    difference = _envelope(coarse) - shared
    normalizer = max(float(np.max(shared)), np.finfo(float).eps)
    return {
        "envelope_nrmse_by_fine_peak": float(np.sqrt(np.mean(difference**2)) / normalizer),
        "max_absolute_difference_by_fine_peak": float(np.max(np.abs(difference)) / normalizer),
    }


def _provenance(path, acquisition):
    return {
        "file": path.name, "sha256": _sha256(path), "name": acquisition.name,
        "citation": acquisition.citation, "channel_shape": list(acquisition.channel_data.shape),
        "sampling_frequency_hz": acquisition.sampling_frequency_hz,
        "sound_speed_m_s": acquisition.sound_speed_m_s,
        "initial_time_s": acquisition.initial_time_s,
        "x_axis_m": acquisition.x_axis_m.tolist(), "z_axis_m": acquisition.z_axis_m.tolist(),
        "element_x_m": acquisition.element_x_m.tolist(),
        "transmit_angles_rad": acquisition.transmit_angles_rad.tolist(),
    }


def _base_report(study):
    return {
        "study": study, "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "numba")},
        "backend": "numba", "dynamic_range_db": 60,
        "processing": "No TGC, denoising, sharpening, registration or learned model",
        "missing_values": "null means undefined/truncated measurement or infinite PSNR",
        "clinical_limit": "Research only; no diagnostic or population-performance claim",
        "datasets": [], "records": [],
    }


def _save_panels(panels, x, z, output, title, kind=None, point_sets=None):
    columns = len(panels) if len(panels) <= 3 else 2
    rows = (len(panels) + columns - 1) // columns
    fig, axes = plt.subplots(
        rows, columns, figsize=(4 * columns, 5 * rows), squeeze=False, layout="constrained"
    )
    extent = [x[0] * 1e3, x[-1] * 1e3, z[-1] * 1e3, z[0] * 1e3]
    for index, (axis, (label, values)) in enumerate(zip(axes.ravel(), panels, strict=True)):
        display = axis.imshow(
            values, cmap="gray", vmin=-60, vmax=0, extent=extent,
            aspect="equal", interpolation="nearest",
        )
        axis.set(title=label, xlabel="Lateral [mm]", ylabel="Depth [mm]")
        if kind == "contrast":
            for depth in (15, 43):
                for radius, color in ((1.5, "#00dbff"), (2.5, "#ffbb00"), (4.5, "#ffbb00")):
                    axis.add_patch(Circle((0, depth), radius, fill=False, color=color, lw=0.8))
        elif kind == "resolution":
            axis.scatter(
                [point[0] * 1e3 for point in NOMINAL_POINT_TARGETS_M],
                [point[1] * 1e3 for point in NOMINAL_POINT_TARGETS_M],
                s=35, facecolors="none", edgecolors="#00dbff", linewidths=0.8,
                label="Nominal search centers",
            )
            if point_sets is not None:
                axis.scatter(
                    [point["detected_x_mm"] for point in point_sets[index]],
                    [point["detected_z_mm"] for point in point_sets[index]],
                    s=25, marker="x", color="#ffbb00", linewidths=0.8,
                    label="Measured peaks",
                )
            if index == 0:
                axis.legend(loc="lower left", fontsize=7)
        axis.set_xlim(extent[0], extent[1])
        axis.set_ylim(extent[2], extent[3])
    fig.suptitle(title)
    fig.colorbar(display, ax=axes.ravel().tolist(), shrink=0.6, label="Normalized amplitude [dB]")
    fig.savefig(output, dpi=160)
    plt.close(fig)


def _measure(kind, envelope, x, z):
    if kind == "contrast":
        return measure_contrast_phantom(envelope, x, z)
    metrics = measure_resolution_phantom(envelope, x, z)
    for direction in ("axial", "lateral"):
        metrics[f"valid_{direction}_targets"] = sum(
            int(np.isfinite(point[f"{direction}_fwhm_mm"])) for point in metrics["points"]
        )
    return metrics


def run_phantom_study(data_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    report = _base_report("Matched-grid physical phantom envelope measurements")
    report.update({
        "f_number": 1.7, "axial_stride": 2, "lateral_stride": 2,
        "reference_policy": "Embedded UFF complex magnitude, sampled on the candidate grid",
        "roi_policy": "Fixed nominal ROIs shared across modes; no registration or retuning",
        "roi_geometry_mm": {
            "cyst_centers": [[0, 15], [0, 43]], "target_radius": 1.5,
            "background_inner_radius": 2.5, "background_outer_radius": 4.5,
            "speckle_center": [10, 28], "speckle_radius": 3,
            "point_search_radius": 4, "point_profile_radius": 2,
        },
        "fwhm_policy": (
            "Half-amplitude width after local 20th-percentile baseline subtraction. "
            "Crossings adjacent to an edge are valid if bracketed; truncated crossings are null. "
            "Seven nominal targets, with valid-count and per-target results; coarse grid limits precision."
        ),
    })
    lines = ["# Analytic physical phantom validation", "",
             "Same RF, angles, F-number 1.7 and stride-2 grid. Measurements use linear envelopes.",
             "The embedded UFF reference is resampled to exactly the same grid.", "",
             "| Phantom | Angles | Mode | Measurement |", "|---|---:|---|---|"]
    figure_links = []
    for kind, filename in (
        ("contrast", "PICMUS_experiment_contrast_speckle.uff"),
        ("resolution", "PICMUS_experiment_resolution_distortion.uff"),
    ):
        path = data_dir / filename
        acquisition = load_picmus_uff(path)
        report["datasets"].append(_provenance(path, acquisition))
        x, z = acquisition.x_axis_m[::2], acquisition.z_axis_m[::2]
        reference = np.abs(acquisition.reference_iq)[::2, ::2]
        reference_metrics = _measure(kind, reference, x, z)
        report["records"].append({
            "kind": kind, "mode": "embedded_reference", "angle_count": None,
            "metrics": reference_metrics,
        })
        for count in (11, 75):
            panels = []
            point_sets = []
            for analytic in (False, True):
                mode = "analytic" if analytic else "legacy"
                result = numba_plane_wave_delay_and_sum(
                    acquisition, angle_count=count, f_number=1.7, analytic=analytic
                )
                np.testing.assert_array_equal(result.x_axis_m, x)
                np.testing.assert_array_equal(result.z_axis_m, z)
                metrics = _measure(kind, _envelope(result), x, z)
                report["records"].append({
                    "kind": kind, "mode": mode, "angle_count": count,
                    "angle_indices": result.angle_indices.tolist(), "metrics": metrics,
                })
                if kind == "contrast":
                    cyst = metrics["cysts"]["deep_cyst"]
                    detail = (f"Deep cyst contrast {cyst['contrast_db']:.2f} dB; "
                              f"CNR {cyst['cnr']:.3f}; gCNR {cyst['generalized_cnr']:.3f}")
                else:
                    point_sets.append(metrics["points"])
                    detail = (f"Median FWHM lateral {metrics['median_lateral_fwhm_mm']:.3f} mm; "
                              f"axial {metrics['median_axial_fwhm_mm']:.3f} mm; "
                              f"valid {metrics['valid_lateral_targets']}/{metrics['valid_axial_targets']}")
                lines.append(f"| {kind} | {count} | {mode} | {detail} |")
                panels.append((f"{mode.capitalize()} · {count} angles", result.bmode_db))
                print(f"{kind}, {count}, {mode}: {detail}", flush=True)
            panels.append(("Embedded UFF reference", log_compress(reference, 60)))
            if kind == "resolution":
                point_sets.append(reference_metrics["points"])
            image_name = f"{kind}_{count}_angles.png"
            _save_panels(panels, x, z, output_dir / image_name,
                         "Physical phantom · fixed ROIs, matched sampling", kind, point_sets)
            figure_links.append(f"[Inspect {kind}, {count} angles]({image_name})")
    lines += ["", " · ".join(figure_links), "", report["fwhm_policy"], "",
              "Nominal target positions are approximate, not certified calibration coordinates.",
              "These metrics do not establish clinical performance or confidence intervals.", "",
              "[Full per-target, shallow/deep cyst and provenance records](metrics.json)", ""]
    clean = finite_json(report)
    (output_dir / "metrics.json").write_text(json.dumps(clean, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return clean


def run_external_study(data_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    report = _base_report("External analytic reconstruction and sparse-angle stability")
    report.update({
        "f_number": 1.5, "axial_stride": 1, "lateral_stride": 1,
        "reference_policy": (
            "No independent reference is available. For each mode, 11 angles are compared only "
            "to that same mode's full-angle reconstruction. Do not interpret this as accuracy "
            "or compare these SSIM values as evidence that one mode is superior."
        ),
        "grid_test": (
            "11-angle linear envelope on stride-2 grid vs shared pixels from stride-1 grid; "
            "normalized by the fine-grid shared envelope peak. This tests numerical grid "
            "consistency, not anatomical correctness. Analytic invariance follows by construction."
        ),
    })
    lines = ["# External analytic validation", "", report["reference_policy"], "",
             "| Acquisition | Mode | 11/full SSIM | Grid envelope NRMSE |",
             "|---|---|---:|---:|"]
    for case in _cases(data_dir):
        if case.identifier not in {"epfl_v5", "epfl_v8", "alpinion_phantom"}:
            continue
        acquisition = _load(case, data_dir)
        provenance = _provenance(case.path, acquisition)
        provenance.update({"subject": case.subject, "platform": case.platform, "probe": case.probe})
        if case.loader == "epfl":
            provenance["settings_sha256"] = {
                name: _sha256(data_dir / "epfl/settings" / name)
                for name in ("beamforming_settings.yaml", "steering_angles.npy", "time_axis.npy")
            }
        report["datasets"].append(provenance)
        panels = []
        for analytic in (False, True):
            mode = "analytic" if analytic else "legacy"
            full_count = acquisition.transmit_angles_rad.size
            fine = numba_plane_wave_delay_and_sum(
                acquisition, angle_count=11, axial_stride=1, lateral_stride=1, analytic=analytic
            )
            full = numba_plane_wave_delay_and_sum(
                acquisition, angle_count=full_count, axial_stride=1, lateral_stride=1,
                analytic=analytic,
            )
            coarse = numba_plane_wave_delay_and_sum(acquisition, angle_count=11, analytic=analytic)
            stability = evaluate_similarity(full.bmode_db, fine.bmode_db).to_dict()
            consistency = grid_consistency(fine, coarse)
            report["records"].append({
                "case": case.identifier, "mode": mode, "full_angle_count": int(full_count),
                "sparse_angle_count": 11, "sparse_angle_indices": fine.angle_indices.tolist(),
                "full_angle_indices": full.angle_indices.tolist(),
                "sparse_to_same_mode_full": stability, "grid_consistency": consistency,
            })
            error = consistency["envelope_nrmse_by_fine_peak"]
            lines.append(f"| {case.identifier} | {mode} | {stability['ssim']:.3f} | {error:.6f} |")
            panels.extend([(f"{mode.capitalize()} · 11 angles", fine.bmode_db),
                           (f"{mode.capitalize()} · full {full_count} angles", full.bmode_db)])
            print(f"{case.identifier}, {mode}: same-mode SSIM {stability['ssim']:.4f}; "
                  f"grid NRMSE {error:.6f}", flush=True)
        _save_panels(panels, fine.x_axis_m, fine.z_axis_m, output_dir / f"{case.identifier}.png",
                     case.label + "\nMeasured RF; no independent image reference")
    lines += ["", report["grid_test"], "",
              "Two public EPFL volunteer acquisitions and one Alpinion physical phantom only.",
              ("[Volunteer 005](epfl_v5.png) · [Volunteer 008](epfl_v8.png) · "
               "[Alpinion phantom](alpinion_phantom.png)"), "",
              "[Full metrics, settings and data checksums](metrics.json)", ""]
    clean = finite_json(report)
    (output_dir / "metrics.json").write_text(json.dumps(clean, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return clean


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/analytic_validation"))
    parser.add_argument("--section", choices=["all", "phantom", "external"], default="all")
    args = parser.parse_args()
    if args.section in {"all", "phantom"}:
        run_phantom_study(args.data_dir, args.output_dir / "phantom")
    if args.section in {"all", "external"}:
        run_external_study(args.data_dir, args.output_dir / "external")


if __name__ == "__main__":
    main()
