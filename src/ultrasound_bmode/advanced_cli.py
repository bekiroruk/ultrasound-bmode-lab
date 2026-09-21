"""Compare conventional and adaptive beamformers on measured PICMUS RF data."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import matplotlib.pyplot as plt

from .metrics import evaluate_similarity
from .real_data import load_picmus_uff, plane_wave_delay_and_sum, reference_bmode

METHODS = ("das", "cf", "pcf", "dmas", "mvdr")


def run_comparison(
    dataset: Path,
    output_dir: Path,
    angle_count: int = 3,
    stride: int = 4,
) -> list[dict[str, float | str]]:
    acquisition = load_picmus_uff(dataset)
    output_dir.mkdir(parents=True, exist_ok=True)
    images = {}
    records: list[dict[str, float | str]] = []
    reference = reference_bmode(acquisition)[::stride, ::stride]

    for method in METHODS:
        start = time.perf_counter()
        result = plane_wave_delay_and_sum(
            acquisition,
            angle_count=angle_count,
            lateral_stride=stride,
            axial_stride=stride,
            method=method,
        )
        runtime = time.perf_counter() - start
        aligned_reference = reference[: result.bmode_db.shape[0], : result.bmode_db.shape[1]]
        metrics = evaluate_similarity(aligned_reference, result.bmode_db)
        record: dict[str, float | str] = {
            "method": method.upper(),
            "angle_count": angle_count,
            "runtime_seconds": runtime,
            "reference_correlation": metrics.correlation,
            "rmse_db": metrics.rmse_db,
            "ssim": metrics.ssim,
            "psnr_db": metrics.psnr_db,
        }
        records.append(record)
        images[method] = result.bmode_db
        print(json.dumps(record, indent=2))

    panels = [(method.upper(), images[method]) for method in METHODS]
    panels.append(("UFF reference", reference))
    fig, axes = plt.subplots(2, 3, figsize=(13.2, 8.8))
    extent = [
        acquisition.x_axis_m[0] * 1e3,
        acquisition.x_axis_m[-1] * 1e3,
        acquisition.z_axis_m[-1] * 1e3,
        acquisition.z_axis_m[0] * 1e3,
    ]
    for axis, (title, image) in zip(axes.ravel(), panels, strict=True):
        axis.imshow(
            image,
            cmap="gray",
            vmin=-60,
            vmax=0,
            extent=extent,
            aspect="equal",
            interpolation="bilinear",
        )
        axis.set(title=title, xlabel="Lateral [mm]", ylabel="Depth [mm]")
    fig.suptitle(
        f"Measured PICMUS carotid RF · {angle_count}-angle beamformer study",
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(output_dir / "adaptive_beamformer_comparison.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    (output_dir / "adaptive_beamformer_metrics.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/raw/PICMUS_carotid_cross.uff"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/adaptive"))
    parser.add_argument("--angles", type=int, default=3)
    parser.add_argument("--stride", type=int, default=4)
    args = parser.parse_args()
    run_comparison(args.dataset, args.output_dir, args.angles, args.stride)
    print(f"Saved adaptive-beamforming artifacts to {args.output_dir}")


if __name__ == "__main__":
    main()
