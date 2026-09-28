"""Compare legacy/analytic carotid ROI metrics with paired spatial-tile uncertainty."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle

from . import __version__
from .accelerated import numba_plane_wave_delay_and_sum, prepare_analytic_channel_cache
from .analytic_validation_cli import _base_report, _provenance
from .interpolation_transfer_cli import _validate_geometry
from .processing import envelope_detect
from .real_data import load_picmus_uff, reference_bmode
from .roi import estimate_translation, locate_carotid_lumen, wall_edge_sharpness
from .spatial_roi import _positive_integer, paired_spatial_bootstrap


def run_analytic_roi(dataset: Path, output_dir: Path, samples=500, seed=7):
    _positive_integer(samples, "samples", 20)
    _positive_integer(seed, "seed", 0)
    acquisition = load_picmus_uff(dataset)
    if acquisition.reference_iq is None:
        raise ValueError("an embedded UFF reference is required to freeze the cross-section ROI")
    if acquisition.transmit_angles_rad.size < 75:
        raise ValueError("the study requires 11 and 75 acquired-angle subsets")
    x, z = acquisition.x_axis_m[::2], acquisition.z_axis_m[::2]
    reference = reference_bmode(acquisition)[::2, ::2]
    if reference.shape != (z.size, x.size):
        raise ValueError("embedded reference shape does not match the physical grid")
    roi = locate_carotid_lumen(reference, x, z)
    envelopes = {"reference": np.abs(acquisition.reference_iq)[::2, ::2]}
    images = {"reference": reference}
    report = _base_report("Fixed carotid ROI: analytic processing and spatial-tile sensitivity")
    report["software_version"] = __version__
    report["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["datasets"] = [_provenance(dataset, acquisition)]
    report["roi_m"] = asdict(roi)
    report["settings"] = {
        "f_number": 1.7, "stride": 2, "angle_counts": [11, 75],
        "dynamic_range_db": 60, "angle_batch_size": 8, "cache_batch_size": 8,
        "bootstrap_samples": samples, "seed": seed, "block_sizes_pixels": [1, 4, 8, 16],
        "sound_speed": "acquisition metadata", "roi_selection": "embedded reference only",
    }
    report["scope"] = (
        "One previously inspected PICMUS human carotid cross-section. The circular heuristic "
        "ROI is not a clinical segmentation and must not be transferred to longitudinal views. "
        "Reference is the same-acquisition embedded UFF reconstruction, not ground truth. "
        "No registration is applied: all results share exact metadata coordinates. "
        "Integer phase-correlation shifts are diagnostic only and do not alter the ROI."
    )
    cache = prepare_analytic_channel_cache(acquisition, batch_size=8)
    comparisons = []
    for count in (11, 75):
        for mode, analytic, method in (
            ("legacy", False, "linear"), ("analytic_linear", True, "linear"),
            ("analytic_cubic", True, "cubic"),
        ):
            name = f"{mode}_{count}"
            result = numba_plane_wave_delay_and_sum(
                acquisition, angle_count=count, f_number=1.7, analytic=analytic,
                interpolation=method, angle_batch_size=8,
                analytic_cache=cache if analytic else None,
                axial_stride=2, lateral_stride=2, dynamic_range_db=60,
            )
            _validate_geometry(acquisition, result, 2, count)
            envelopes[name] = np.abs(result.rf) if analytic else envelope_detect(result.rf)
            images[name] = result.bmode_db
            report["records"].append({
                "name": name, "analytic": analytic, "interpolation": method,
                "angle_count": count, "angle_indices": result.angle_indices.tolist(),
                "diagnostic_shift_axial_lateral_pixels": list(
                    estimate_translation(reference, result.bmode_db)),
                "unregistered_wall_gradient_db_per_mm": wall_edge_sharpness(
                    result.bmode_db, x, z, roi),
            })
        comparisons.extend(((f"analytic_linear_{count}", f"legacy_{count}"),
                            (f"analytic_cubic_{count}", f"analytic_linear_{count}")))
    report["spatial_bootstrap"] = []
    for size in report["settings"]["block_sizes_pixels"]:
        row = paired_spatial_bootstrap(
            envelopes, x, z, roi, block_size=size, samples=samples, seed=seed,
            comparisons=tuple(comparisons),
        )
        report["spatial_bootstrap"].append(row)
        print(f"Block {size}x{size}: {row['occupied_blocks']} tiles; "
              f"{row['rejected_insufficient_support_draws']} rejected draws", flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    _save_report(report, output_dir)
    _save_images(images, x, z, roi, output_dir)
    return report


def _save_images(images, x, z, roi, output_dir):
    fig, axes = plt.subplots(2, 4, figsize=(15, 10), layout="constrained")
    extent = (x[0] * 1e3, x[-1] * 1e3, z[-1] * 1e3, z[0] * 1e3)
    for row, count in enumerate((11, 75)):
        names = ["reference", f"legacy_{count}", f"analytic_linear_{count}",
                 f"analytic_cubic_{count}"]
        for axis, name in zip(axes[row], names, strict=True):
            plot = axis.imshow(images[name], extent=extent, aspect="equal", cmap="gray",
                               vmin=-60, vmax=0, interpolation="nearest")
            for radius, color in ((roi.radius_m, "#00e5ff"),
                                  (roi.radius_m + 1e-3, "#ffcc00"),
                                  (roi.radius_m + 3e-3, "#ffcc00")):
                axis.add_patch(Circle((roi.center_x_m * 1e3, roi.center_z_m * 1e3),
                                      radius * 1e3, fill=False, color=color, linewidth=1))
            axis.set(title=name.replace("_", " "), xlabel="Lateral [mm]", ylabel="Depth [mm]")
    fig.colorbar(plot, ax=axes, shrink=0.65, label="Peak-normalized amplitude [dB]")
    fig.suptitle("Fixed reference-selected ROI; no registration or per-method ROI tuning\n"
                 "Cyan: lumen target; yellow: background annulus boundaries")
    fig.savefig(output_dir / "analytic_roi.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def _save_report(report, output_dir):
    studies = report["spatial_bootstrap"]
    labels = [f"{row['block_size_pixels'][0]}×{row['block_size_pixels'][1]}" for row in studies]
    lines = ["# Analytic carotid ROI and spatial uncertainty", "", report["scope"], "",
             "F/1.7, stride 2, metadata sound speed; no TGC or denoising. Metrics use linear",
             "envelopes; figures use separately peak-normalized 60 dB displays.", "",
             "## Fixed-ROI estimates and block-size sensitivity", "",
             "Intervals below are conditional 2.5–97.5 percentile resampling ranges, not",
             "validated clinical confidence intervals. The 1×1 case is an occupied-pixel",
             "baseline, not the legacy stratified fixed-sample-count pixel bootstrap.", "",
             "| Image | Contrast dB | CNR | gCNR | gCNR interval " + " | ".join(labels) + " |",
             "|---|---:|---:|---:|" + "---|" * len(studies)]
    for name, metrics in studies[0]["images"].items():
        intervals = [row["images"][name]["generalized_cnr"]["percentile95"] for row in studies]
        lines.append(f"| {name} | {metrics['contrast_db']['estimate']:.2f} | "
                     f"{metrics['cnr']['estimate']:.3f} | "
                     f"{metrics['generalized_cnr']['estimate']:.3f} | "
                     + " | ".join(f"[{lo:.3f}, {hi:.3f}]" for lo, hi in intervals) + " |")
    lines += ["", "## Paired changes: first minus second", "",
              "Both methods receive exactly the same tile draws. Differences are conditional",
              "ROI metric changes, not diagnostic improvement or a population hypothesis test.", "",
              "| Comparison | Block pixels | gCNR change | Percentile range |",
              "|---|---:|---:|---|"]
    for row in studies:
        for difference in row["paired_differences"]:
            metric = difference["metrics"]["generalized_cnr"]
            lo, hi = metric["percentile95"]
            lines.append(f"| {difference['first']} − {difference['second']} | "
                         f"{row['block_size_pixels'][0]} | {metric['estimate']:+.4f} | "
                         f"[{lo:+.4f}, {hi:+.4f}] |")
    lines += ["", "## Resampling protocol and limitations", "", studies[0]["limitations"], "",
              studies[0]["gcnr_estimator"], "",
              "All ROI-intersecting tiles are sampled with replacement. Partial boundary tiles",
              "retain all included pixels; the same multiplicities apply to every image.",
              "This exploratory cluster-resampling implementation does not estimate an optimal",
              "block size or calibrate interval coverage. The annulus may include heterogeneous",
              "tissue; ROI selection and tile-origin sensitivity are not included.", "",
              "Background on dependent-data resampling: [Shalizi, bootstrap lecture]",
              "(https://www.stat.cmu.edu/~cshalizi/dst/20/lectures/16/lecture-16.html).",
              "This is motivation, not a proof of coverage for these image metrics.", "",
              "![Matched ROI overlays](analytic_roi.png)", "",
              "[Full settings, provenance, block support and all metric intervals](metrics.json)", ""]
    # Keep the Markdown reference link contiguous.
    text = "\n".join(lines).replace("lecture]\n(", "lecture](")
    (output_dir / "README.md").write_text(text, encoding="utf-8")
    (output_dir / "metrics.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/raw/PICMUS_carotid_cross.uff"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/analytic_roi"))
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    run_analytic_roi(args.dataset, args.output_dir, args.samples, args.seed)


if __name__ == "__main__":
    main()
