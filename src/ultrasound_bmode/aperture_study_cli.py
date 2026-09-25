"""Explore analytic receive F-number without silently changing reconstruction defaults."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .accelerated import numba_plane_wave_delay_and_sum
from .analytic_validation_cli import _base_report, _measure, _provenance, _save_panels, finite_json
from .real_data import load_picmus_uff

F_NUMBERS = (0.8, 1.0, 1.2, 1.5, 1.7, 2.0, 2.5)


def select_candidate(records, baseline_f_number=1.7):
    """Exploratory 11-angle selection with predeclared contrast/axial guardrails."""
    rows = [row for row in records if row["angle_count"] == 11 and row["stride"] == 2]
    baseline = next((row for row in rows if row["f_number"] == baseline_f_number), None)
    if baseline is None or not _valid_measurements(baseline):
        raise ValueError("selection requires a valid 11-angle stride-2 baseline")
    eligible = []
    for row in rows:
        resolution = row["resolution"]
        widths = [resolution[f"median_{direction}_fwhm_mm"] for direction in ("axial", "lateral")]
        if not _valid_measurements(row):
            continue
        if widths[0] > baseline["resolution"]["median_axial_fwhm_mm"] * 1.05:
            continue
        if any(row["contrast"]["cysts"][cyst]["generalized_cnr"] <
               baseline["contrast"]["cysts"][cyst]["generalized_cnr"] - 0.02
               for cyst in ("shallow_cyst", "deep_cyst")):
            continue
        eligible.append(row)
    if not eligible:
        return None
    return min(eligible, key=lambda row: row["resolution"]["median_lateral_fwhm_mm"])["f_number"]


def _valid_measurements(row):
    resolution = row["resolution"]
    widths = [resolution[f"median_{direction}_fwhm_mm"] for direction in ("axial", "lateral")]
    gcnrs = [row["contrast"]["cysts"][cyst]["generalized_cnr"]
             for cyst in ("shallow_cyst", "deep_cyst")]
    return (all(value is not None and np.isfinite(value) and value > 0 for value in widths)
            and all(value is not None and np.isfinite(value) and 0 <= value <= 1 for value in gcnrs)
            and resolution["valid_axial_targets"] == 7
            and resolution["valid_lateral_targets"] == 7)


def _evaluate(contrast, resolution, f_number, count, stride):
    images = {}
    row = {"f_number": f_number, "angle_count": count, "stride": stride}
    for kind, acquisition in (("contrast", contrast), ("resolution", resolution)):
        result = numba_plane_wave_delay_and_sum(
            acquisition, angle_count=count, f_number=f_number, analytic=True,
            lateral_stride=stride, axial_stride=stride,
        )
        row[kind] = _measure(kind, np.abs(result.rf), result.x_axis_m, result.z_axis_m)
        row["angle_indices"] = result.angle_indices.tolist()
        images[kind] = result
    return row, images


def _plot_tradeoffs(rows, output):
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), layout="constrained")
    series = [
        ("Median lateral FWHM [mm]", lambda row: row["resolution"]["median_lateral_fwhm_mm"]),
        ("Median axial FWHM [mm]", lambda row: row["resolution"]["median_axial_fwhm_mm"]),
        ("Shallow cyst gCNR", lambda row: row["contrast"]["cysts"]["shallow_cyst"]["generalized_cnr"]),
        ("Deep cyst gCNR", lambda row: row["contrast"]["cysts"]["deep_cyst"]["generalized_cnr"]),
    ]
    for axis, (label, value) in zip(axes.ravel(), series, strict=True):
        for count, style in ((11, "o-"), (75, "s--")):
            selected = [row for row in rows if row["angle_count"] == count and row["stride"] == 2]
            axis.plot([row["f_number"] for row in selected], [value(row) for row in selected],
                      style, label=f"{count} angles")
        axis.axvline(1.7, color="gray", linestyle=":", label="Baseline F/1.7")
        axis.set(xlabel="Receive F-number (lower = wider aperture)", ylabel=label)
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    fig.suptitle("Measured phantom · analytic CPWC aperture tradeoffs")
    fig.savefig(output, dpi=170)
    plt.close(fig)


def run_aperture_study(data_dir: Path, output_dir: Path):
    paths = [data_dir / f"PICMUS_experiment_{name}.uff"
             for name in ("contrast_speckle", "resolution_distortion")]
    contrast, resolution = [load_picmus_uff(path) for path in paths]
    output_dir.mkdir(parents=True, exist_ok=True)
    report = _base_report("Exploratory F-number sweep on two measured phantom acquisitions")
    report.update({
        "datasets": [_provenance(path, acquisition)
                     for path, acquisition in zip(paths, (contrast, resolution), strict=True)],
        "f_numbers": list(F_NUMBERS), "baseline_f_number": 1.7,
        "selection_rule": (
            "Select minimum median lateral FWHM at 11 angles / stride 2, requiring all seven "
            "widths valid in both directions, median axial FWHM <= 1.05 times baseline, and "
            "each cyst gCNR no more than 0.02 below baseline. Includes baseline as fallback."
        ),
        "validation_limit": (
            "Exploratory selection on the measured phantom, not independent validation. "
            "75-angle and finer-grid checks reuse these same acquisitions. No defaults changed; "
            "do not claim generalization to human data or clinical benefit. The candidate may "
            "lie at the sweep boundary; this is not evidence of a global optimum."
        ),
        "roi_policy": "Same fixed linear-envelope ROIs and baseline-corrected FWHM as v0.5",
    })
    for count in (11, 75):
        for f_number in F_NUMBERS:
            row, _ = _evaluate(contrast, resolution, f_number, count, 2)
            report["records"].append(row)
            print(f"{count} angles, F/{f_number}: lateral "
                  f"{row['resolution']['median_lateral_fwhm_mm']:.4f} mm", flush=True)
    selected = select_candidate(report["records"])
    report["selected_f_number"] = selected
    if selected is not None:
        # A finer-grid repeat tests whether the apparent gain is only a sampling artifact.
        fine_images = {}
        for f_number in dict.fromkeys((1.7, selected)):
            row, images = _evaluate(contrast, resolution, f_number, 11, 1)
            report["records"].append(row)
            fine_images[f_number] = images
        for kind in ("contrast", "resolution"):
            panels, point_sets = [], []
            for f_number, images in fine_images.items():
                result = images[kind]
                panels.append((f"Analytic · F/{f_number} · 11 angles", result.bmode_db))
                if kind == "resolution":
                    point_sets.append(_measure(kind, np.abs(result.rf), result.x_axis_m,
                                               result.z_axis_m)["points"])
            _save_panels(panels, result.x_axis_m, result.z_axis_m, output_dir / f"{kind}_fine.png",
                         "Finer-grid repeat · same phantom, not a held-out test", kind, point_sets)
    _plot_tradeoffs(report["records"], output_dir / "aperture_tradeoffs.png")
    lines = ["# Analytic receive-aperture study", "", report["selection_rule"], "",
             f"Selected exploratory candidate: **F/{selected}**. No reconstruction defaults changed.",
             "", report["validation_limit"], "",
             "| Angles | Grid stride | F-number | Lateral FWHM mm | Axial FWHM mm | Shallow gCNR | Deep gCNR |",
             "|---:|---:|---:|---:|---:|---:|---:|"]
    for row in report["records"]:
        res, cysts = row["resolution"], row["contrast"]["cysts"]
        lines.append(f"| {row['angle_count']} | {row['stride']} | {row['f_number']} | "
                     f"{res['median_lateral_fwhm_mm']:.4f} | {res['median_axial_fwhm_mm']:.4f} | "
                     f"{cysts['shallow_cyst']['generalized_cnr']:.4f} | "
                     f"{cysts['deep_cyst']['generalized_cnr']:.4f} |")
    lines += ["", "![Tradeoffs](aperture_tradeoffs.png)", "",
              "[Fine-grid contrast](contrast_fine.png) · [Fine-grid resolution](resolution_fine.png)",
              "", "[All points, measurements and data provenance](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "metrics.json").write_text(
        json.dumps(finite_json(report), indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/aperture_study"))
    args = parser.parse_args()
    run_aperture_study(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
