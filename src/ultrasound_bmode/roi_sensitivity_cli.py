"""Frozen ROI/partition-origin sensitivity on two measured human acquisitions."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle

from . import __version__
from .accelerated import numba_plane_wave_delay_and_sum, prepare_analytic_channel_cache
from .analytic_validation_cli import _base_report, _provenance
from .external_validation_cli import _cases, _load
from .interpolation_transfer_cli import SETTINGS_FILES, _validate_geometry
from .real_data import reference_bmode
from .reconstruction_quality_cli import _sha256
from .roi import LumenRoi, locate_carotid_lumen
from .spatial_roi import _positive_integer, paired_spatial_bootstrap


def sensitivity_conditions(roi):
    """One-factor-at-a-time conditions, fixed before viewing metric results."""
    conditions = [("baseline", roi, (0, 0))]
    for field, label, delta in (
        ("center_x_m", "x", 0.5e-3), ("center_z_m", "z", 0.5e-3),
        ("radius_m", "radius", 0.3e-3),
    ):
        for sign in (-1, 1):
            conditions.append((f"{label}_{'minus' if sign < 0 else 'plus'}",
                               replace(roi, **{field: getattr(roi, field) + sign * delta}),
                               (0, 0)))
    conditions.extend((f"origin_{a}_{b}", roi, (a, b))
                      for a, b in ((0, 4), (4, 0), (4, 4)))
    return conditions


def summarize(records):
    summaries = []
    cases = list(dict.fromkeys(row["case"] for row in records))
    for case in cases:
        rows = [row for row in records if row["case"] == case]
        baseline = next(row for row in rows if row["condition"] == "baseline")
        for index, pair in enumerate(baseline["bootstrap"]["paired_differences"]):
            roi_rows = [row for row in rows if not row["condition"].startswith("origin_")]
            origin_rows = [row for row in rows
                           if row["condition"] == "baseline"
                           or row["condition"].startswith("origin_")]
            estimates = [row["bootstrap"]["paired_differences"][index]["metrics"]
                         ["generalized_cnr"]["estimate"] for row in roi_rows]
            intervals = [row["bootstrap"]["paired_differences"][index]["metrics"]
                         ["generalized_cnr"]["percentile95"] for row in origin_rows]
            summaries.append({
                "case": case, "first": pair["first"], "second": pair["second"],
                "baseline_delta_gcnr": pair["metrics"]["generalized_cnr"]["estimate"],
                "roi_delta_gcnr_min_max": [min(estimates), max(estimates)],
                "roi_point_sign_changes": min(estimates) < 0 < max(estimates),
                "origin_interval_lower_min_max": [min(v[0] for v in intervals),
                                                  max(v[0] for v in intervals)],
                "origin_interval_upper_min_max": [min(v[1] for v in intervals),
                                                  max(v[1] for v in intervals)],
                "origin_intervals_containing_zero": sum(lo <= 0 <= hi for lo, hi in intervals),
                "origin_count": len(intervals),
            })
    return summaries


def run_roi_sensitivity(data_dir: Path, output_dir: Path, samples=500, seed=7):
    _positive_integer(samples, "samples", 20)
    _positive_integer(seed, "seed", 0)
    cases = [case for case in _cases(data_dir) if case.identifier in ("picmus_cross", "epfl_v5")]
    required = [case.path for case in cases]
    required += [data_dir / "epfl/settings" / name for name in SETTINGS_FILES]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing study inputs: " + ", ".join(missing))
    report = _base_report("ROI and spatial partition-origin sensitivity")
    report.update({
        "software_version": __version__, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "settings": {"f_number": 1.7, "analytic": True, "angle_batch_size": 8,
                     "cache_batch_size": 8, "samples": samples, "seed": seed,
                     "block_size_pixels": 8, "center_offsets_mm": [-0.5, 0.5],
                     "radius_offsets_mm": [-0.3, 0.3],
                     "origins_axial_lateral_pixels": [[0, 0], [0, 4], [4, 0], [4, 4]]},
        "scope": (
            "Two previously inspected human acquisitions, not a new blinded clinical cohort. "
            "PICMUS ROI is selected once from the embedded reference. EPFL volunteer 005 "
            "ROI is manually frozen at x=6 mm, z=17 mm, radius=2.2 mm after viewing the "
            "previous full-angle linear image, before this study's metrics. EPFL has no "
            "independent image reference or expert segmentation; selection bias remains. "
            "PICMUS subject identity is unavailable; no assumption of participant independence."
        ),
        "protocol": (
            "Ten one-factor-at-a-time conditions per acquisition: baseline; four ±0.5 mm "
            "center shifts; two ±0.3 mm radius changes; three half-block origin shifts. "
            "Annulus radii remain target radius +1/+3 mm. No optimum is selected. "
            "Each condition freezes the same masks and paired tile draws for linear/cubic "
            "at 11/full angles. Same pixel-sized blocks have different physical dimensions "
            "across grids; physical sizes and counts are reported, not pooled."
        ),
        "limitations": (
            "Sensitivity ranges are not confidence intervals and do not incorporate ROI "
            "uncertainty into the bootstrap intervals. No factorial ROI/origin interactions, "
            "coverage calibration, histogram-bin sensitivity, observer or population inference. "
            "Resampling retains only within-block dependence; finite heterogeneous masks and "
            "manual/algorithmic region selection limit interpretation. Defaults stay unchanged."
        ),
    })
    output_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        acquisition = _load(case, data_dir)
        stride = 2 if acquisition.reference_iq is not None else 1
        x, z = acquisition.x_axis_m[::stride], acquisition.z_axis_m[::stride]
        if case.identifier == "picmus_cross":
            roi = locate_carotid_lumen(reference_bmode(acquisition)[::stride, ::stride], x, z)
            selection = "embedded UFF reference heuristic, fixed before candidate metrics"
        else:
            roi = LumenRoi(6e-3, 17e-3, 2.2e-3)
            selection = "manual from previously inspected full-angle linear image; not ground truth"
        metadata = _provenance(case.path, acquisition)
        metadata.update(case=case.identifier, subject=case.subject, roi_m=asdict(roi),
                        roi_selection=selection, stride=stride,
                        independent_reference_available=False)
        if case.loader == "epfl":
            metadata["settings_sha256"] = {
                name: _sha256(data_dir / "epfl/settings" / name) for name in SETTINGS_FILES}
        report["datasets"].append(metadata)
        cache = prepare_analytic_channel_cache(acquisition, batch_size=8)
        envelopes, images, pairs = {}, {}, []
        counts = (11, int(acquisition.transmit_angles_rad.size))
        for count in counts:
            for method in ("linear", "cubic"):
                name = f"{method}_{count}"
                result = numba_plane_wave_delay_and_sum(
                    acquisition, angle_count=count, analytic=True, interpolation=method,
                    f_number=1.7, angle_batch_size=8, analytic_cache=cache,
                    lateral_stride=stride, axial_stride=stride, dynamic_range_db=60)
                _validate_geometry(acquisition, result, stride, count)
                envelopes[name], images[name] = np.abs(result.rf), result.bmode_db
                metadata.setdefault("selected_angle_indices", {})[str(count)] = (
                    result.angle_indices.tolist())
            pairs.append((f"cubic_{count}", f"linear_{count}"))
        conditions = sensitivity_conditions(roi)
        for label, current_roi, origin in conditions:
            bootstrap = paired_spatial_bootstrap(
                envelopes, x, z, current_roi, block_size=8, block_origin=origin,
                samples=samples, seed=seed, comparisons=tuple(pairs))
            report["records"].append({"case": case.identifier, "condition": label,
                                      "roi_m": asdict(current_roi), "bootstrap": bootstrap})
            print(f"{case.identifier}: {label} complete", flush=True)
        _plot(images, x, z, roi, conditions, counts, case.label,
              output_dir / f"{case.identifier}.png")
        del acquisition, cache
    report["summaries"] = summarize(report["records"])
    _save_report(report, output_dir)
    return report


def _plot(images, x, z, roi, conditions, counts, label, path):
    fig, axes = plt.subplots(2, 2, figsize=(10, 10), layout="constrained")
    for row, count in enumerate(counts):
        for col, method in enumerate(("linear", "cubic")):
            axis = axes[row, col]
            plot = axis.imshow(images[f"{method}_{count}"], cmap="gray", vmin=-60, vmax=0,
                               extent=(x[0]*1e3, x[-1]*1e3, z[-1]*1e3, z[0]*1e3),
                               aspect="equal", interpolation="nearest")
            for _, perturbed, _ in conditions[1:7]:
                axis.add_patch(Circle((perturbed.center_x_m*1e3, perturbed.center_z_m*1e3),
                                      perturbed.radius_m*1e3, fill=False, color="#ef80e8",
                                      linewidth=0.6, alpha=0.65))
            for radius, color in ((roi.radius_m, "#00e5ff"),
                                  (roi.radius_m + 1e-3, "#ffcc00"),
                                  (roi.radius_m + 3e-3, "#ffcc00")):
                axis.add_patch(Circle((roi.center_x_m*1e3, roi.center_z_m*1e3), radius*1e3,
                                      fill=False, color=color, linewidth=1))
            axis.set(title=f"{method} · {count} angles", xlabel="Lateral [mm]", ylabel="Depth [mm]")
    fig.colorbar(plot, ax=axes, shrink=0.6, label="Peak-normalized amplitude [dB]")
    fig.suptitle(label + "\nCyan: baseline target; yellow: baseline annulus; pink: ROI variants\n"
                 "Variants are sensitivity checks, not optimized or expert segmentations")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _save_report(report, output_dir):
    lines = ["# Human ROI and block-origin sensitivity", "", report["scope"], "",
             report["protocol"], "", report["limitations"], "",
             ("| Case | Cubic − linear | Baseline ΔgCNR | ROI perturbation min–max | "
              "Point sign changes? | Origin intervals including zero |"),
             "|---|---|---:|---|---|---|"]
    for row in report["summaries"]:
        low, high = row["roi_delta_gcnr_min_max"]
        lines.append(f"| {row['case']} | {row['first']} − {row['second']} | "
                     f"{row['baseline_delta_gcnr']:+.4f} | [{low:+.4f}, {high:+.4f}] | "
                     f"{row['roi_point_sign_changes']} | "
                     f"{row['origin_intervals_containing_zero']}/{row['origin_count']} |")
    lines += ["", "The min–max column spans seven fixed ROI choices, not a confidence interval.",
              "Origin tests change only tile partitioning: point estimates and pixel masks",
              "must remain unchanged. See JSON for all contrast/CNR/gCNR intervals, paired",
              "deltas, physical block sizes, geometry, source/settings hashes and rejected draws.",
              "", "![PICMUS ROI variants](picmus_cross.png)", "",
              "![EPFL volunteer 005 ROI variants](epfl_v5.png)", "",
              "[Full numerical evidence](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "metrics.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/roi_sensitivity"))
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    run_roi_sensitivity(args.data_dir, args.output_dir, args.samples, args.seed)


if __name__ == "__main__":
    main()
