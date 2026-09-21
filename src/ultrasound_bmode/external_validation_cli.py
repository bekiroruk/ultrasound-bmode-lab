"""Run multi-acquisition, multi-subject, and cross-platform RF validation."""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .accelerated import numba_plane_wave_delay_and_sum
from .epfl import load_epfl_acquisition
from .metrics import evaluate_similarity
from .real_data import load_uff_channel_data, reference_bmode


@dataclass(frozen=True)
class ValidationCase:
    identifier: str
    label: str
    path: Path
    loader: str
    subject: str
    platform: str
    probe: str
    anatomy: str


def _parse_counts(value: str) -> tuple[int, ...]:
    counts = tuple(dict.fromkeys(int(item.strip()) for item in value.split(",") if item.strip()))
    if not counts or any(count <= 0 for count in counts):
        raise argparse.ArgumentTypeError("counts must be positive comma-separated integers")
    return counts


def _cases(data_dir: Path) -> tuple[ValidationCase, ...]:
    return (
        ValidationCase(
            "picmus_cross",
            "PICMUS carotid · cross",
            data_dir / "PICMUS_carotid_cross.uff",
            "uff",
            "PICMUS volunteer; public ID unavailable",
            "Verasonics Vantage 256",
            "L11/L11-4v",
            "carotid cross-section",
        ),
        ValidationCase(
            "picmus_long",
            "PICMUS carotid · longitudinal",
            data_dir / "PICMUS_carotid_long.uff",
            "uff",
            "PICMUS volunteer; public ID unavailable",
            "Verasonics Vantage 256",
            "L11/L11-4v",
            "carotid longitudinal",
        ),
        ValidationCase(
            "epfl_v5",
            "EPFL volunteer 005 · carotid",
            data_dir / "epfl/invivo_14965.npz",
            "epfl",
            "EPFL volunteer 005",
            "EPFL Verasonics acquisition",
            "GE 9L-D",
            "carotid",
        ),
        ValidationCase(
            "epfl_v8",
            "EPFL volunteer 008 · carotid",
            data_dir / "epfl/invivo_18198.npz",
            "epfl",
            "EPFL volunteer 008",
            "EPFL Verasonics acquisition",
            "GE 9L-D",
            "carotid",
        ),
        ValidationCase(
            "alpinion_phantom",
            "Alpinion · hypoechoic phantom",
            data_dir / "Alpinion_L3-8_CPWC_hypoechoic.uff",
            "uff",
            "physical phantom",
            "Alpinion research acquisition",
            "L3-8",
            "hypoechoic phantom",
        ),
    )


def _load(case: ValidationCase, data_dir: Path):
    if case.loader == "epfl":
        return load_epfl_acquisition(case.path, data_dir / "epfl/settings")
    return load_uff_channel_data(case.path)


def _save_image_grid(
    panels: list[tuple[ValidationCase, np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    output: Path,
) -> None:
    fig, axes = plt.subplots(len(panels), 2, figsize=(10.5, 3.6 * len(panels)), squeeze=False)
    for row, (case, reference, candidate, x_axis, z_axis) in enumerate(panels):
        extent = [x_axis[0] * 1e3, x_axis[-1] * 1e3, z_axis[-1] * 1e3, z_axis[0] * 1e3]
        for axis, title, image in (
            (axes[row, 0], f"{case.label}\nreference", reference),
            (axes[row, 1], f"{case.label}\n11-angle CPWC", candidate),
        ):
            axis.imshow(
                image,
                cmap="gray",
                vmin=-60,
                vmax=0,
                extent=extent,
                aspect="auto",
                interpolation="bilinear",
            )
            axis.set(title=title, xlabel="Lateral [mm]", ylabel="Depth [mm]")
    fig.suptitle("External RF validation across acquisitions, subjects, and probes", fontweight="bold")
    fig.tight_layout()
    fig.savefig(output, dpi=170, bbox_inches="tight")
    plt.close(fig)


def _save_metric_plot(records: list[dict[str, object]], cases: tuple[ValidationCase, ...], output: Path) -> None:
    counts = sorted({int(record["angle_count"]) for record in records})
    positions = np.arange(len(cases), dtype=float)
    width = 0.78 / len(counts)
    fig, axis = plt.subplots(figsize=(11.5, 4.8))
    for count_index, count in enumerate(counts):
        values = [
            float(next(record["correlation"] for record in records if record["case"] == case.identifier and record["angle_count"] == count))
            for case in cases
        ]
        offset = (count_index - (len(counts) - 1) / 2.0) * width
        unit = "angle" if count == 1 else "angles"
        axis.bar(positions + offset, values, width, label=f"{count} {unit}")
    axis.set(
        xticks=positions,
        xticklabels=[case.label.replace(" · ", "\n") for case in cases],
        ylabel="Correlation to case reference",
        ylim=(0, 1),
        title="Sparse-angle robustness on independent measured RF acquisitions",
    )
    axis.grid(axis="y", alpha=0.25)
    axis.legend(ncol=len(counts))
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def run_external_validation(
    data_dir: Path,
    output_dir: Path,
    counts: tuple[int, ...] = (1, 3, 11),
) -> dict[str, object]:
    cases = _cases(data_dir)
    missing = [str(case.path) for case in cases if not case.path.is_file()]
    if missing:
        raise FileNotFoundError("Missing validation data:\n" + "\n".join(missing))
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    panels = []
    backend_warmed = False

    for case in cases:
        acquisition = _load(case, data_dir)
        if max(counts) > acquisition.transmit_angles_rad.size:
            raise ValueError(f"{case.identifier} has fewer angles than requested")
        if not backend_warmed:
            numba_plane_wave_delay_and_sum(
                acquisition, angle_count=1, lateral_stride=1000, axial_stride=1000
            )
            backend_warmed = True
        if acquisition.reference_iq is not None:
            lateral_stride = axial_stride = 2
            reference = reference_bmode(acquisition)[::axial_stride, ::lateral_stride]
            reference_type = "embedded UFF beamformed reference"
        else:
            lateral_stride = axial_stride = 1
            full = numba_plane_wave_delay_and_sum(
                acquisition,
                angle_count=acquisition.transmit_angles_rad.size,
                lateral_stride=lateral_stride,
                axial_stride=axial_stride,
            )
            reference = full.bmode_db
            reference_type = f"full {acquisition.transmit_angles_rad.size}-angle CPWC"

        case_images = {}
        for count in counts:
            start = time.perf_counter()
            result = numba_plane_wave_delay_and_sum(
                acquisition,
                angle_count=count,
                lateral_stride=lateral_stride,
                axial_stride=axial_stride,
            )
            runtime = time.perf_counter() - start
            aligned_reference = reference[: result.bmode_db.shape[0], : result.bmode_db.shape[1]]
            metrics = evaluate_similarity(aligned_reference, result.bmode_db)
            record = {
                "case": case.identifier,
                "label": case.label,
                "subject": case.subject,
                "platform": case.platform,
                "probe": case.probe,
                "anatomy": case.anatomy,
                "reference_type": reference_type,
                "acquired_angles": int(acquisition.transmit_angles_rad.size),
                "angle_count": count,
                "runtime_seconds": runtime,
                "correlation": metrics.correlation,
                "rmse_db": metrics.rmse_db,
                "ssim": metrics.ssim,
                "psnr_db": metrics.psnr_db,
            }
            records.append(record)
            case_images[count] = result
            print(json.dumps(record, indent=2))

        display_count = 11 if 11 in case_images else max(case_images)
        display = case_images[display_count]
        panels.append((case, reference, display.bmode_db, display.x_axis_m, display.z_axis_m))

    human_records = [record for record in records if record["subject"] != "physical phantom"]
    summary = {
        "study_design": {
            "measured_acquisitions": len(cases),
            "human_acquisitions": 4,
            "explicitly_distinct_epfl_volunteers": 2,
            "physical_phantom_acquisitions": 1,
            "probe_models": ["L11/L11-4v", "GE 9L-D", "Alpinion L3-8"],
            "important_limit": (
                "EPFL comparisons use the same acquisition's full 87-angle CPWC as reference; "
                "they test sparse-angle stability, not clinical accuracy."
            ),
        },
        "human_11_angle_mean_correlation": float(
            np.mean([record["correlation"] for record in human_records if record["angle_count"] == 11])
        ),
        "records": records,
    }
    (output_dir / "external_validation.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "external_validation.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    _save_image_grid(panels, output_dir / "external_validation_images.png")
    _save_metric_plot(records, cases, output_dir / "external_validation_metrics.png")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/external_validation"))
    parser.add_argument("--counts", type=_parse_counts, default=_parse_counts("1,3,11"))
    args = parser.parse_args()
    run_external_validation(args.data_dir, args.output_dir, args.counts)
    print(f"Saved external validation artifacts to {args.output_dir}")


if __name__ == "__main__":
    main()
