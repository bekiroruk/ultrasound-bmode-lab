"""Benchmark plane-wave angle count against reference quality and runtime."""

from __future__ import annotations

import argparse
import csv
import gc
import json
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import psutil
from matplotlib.ticker import ScalarFormatter

from .metrics import evaluate_similarity
from .real_data import load_picmus_uff, plane_wave_delay_and_sum, reference_bmode


def _parse_counts(value: str) -> list[int]:
    counts = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not counts or any(count <= 0 for count in counts):
        raise argparse.ArgumentTypeError("angle counts must be positive comma-separated integers")
    return list(dict.fromkeys(counts))


def _aligned_reference(acquisition, shape: tuple[int, int]) -> np.ndarray:
    reference = reference_bmode(acquisition)[::2, ::2]
    return reference[: shape[0], : shape[1]]


def _save_reconstruction_grid(acquisition, images: dict[int, np.ndarray], output: Path) -> None:
    counts = list(images)
    panels = [(f"Our CPWC · {count} angle{'s' if count != 1 else ''}", images[count]) for count in counts]
    panels.append(("UFF reference · 75 angles", reference_bmode(acquisition)[::2, ::2]))
    columns = 3
    rows = int(np.ceil(len(panels) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(13.2, 4.5 * rows), squeeze=False)
    extent = [
        acquisition.x_axis_m[0] * 1e3,
        acquisition.x_axis_m[-1] * 1e3,
        acquisition.z_axis_m[-1] * 1e3,
        acquisition.z_axis_m[0] * 1e3,
    ]
    for axis, (title, image) in zip(axes.ravel(), panels, strict=False):
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
    for axis in axes.ravel()[len(panels) :]:
        axis.axis("off")
    fig.suptitle("Measured PICMUS carotid RF · angle-count study", fontweight="bold")
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _save_tradeoff_plot(records: list[dict[str, float]], output: Path) -> None:
    counts = np.array([record["angle_count"] for record in records])
    runtime = np.array([record["runtime_seconds"] for record in records])
    correlation = np.array([record["reference_correlation"] for record in records])
    ssim = np.array([record["ssim"] for record in records])

    fig, (quality_ax, runtime_ax) = plt.subplots(1, 2, figsize=(11.5, 4.3))
    quality_ax.plot(counts, correlation, "o-", linewidth=2, label="Correlation")
    quality_ax.plot(counts, ssim, "s-", linewidth=2, label="SSIM")
    quality_ax.set(
        xlabel="Compounded plane waves",
        ylabel="Similarity to UFF reference",
        xscale="log",
        xticks=counts,
        ylim=(0, 1),
    )
    quality_ax.get_xaxis().set_major_formatter(ScalarFormatter())
    quality_ax.grid(alpha=0.25)
    quality_ax.legend()

    runtime_ax.plot(counts, runtime, "o-", color="#d1495b", linewidth=2)
    runtime_ax.set(
        xlabel="Compounded plane waves",
        ylabel="CPU runtime [s]",
        xscale="log",
        yscale="log",
        xticks=counts,
    )
    runtime_ax.get_xaxis().set_major_formatter(ScalarFormatter())
    runtime_ax.grid(alpha=0.25)
    fig.suptitle("Image quality / compute trade-off", fontweight="bold")
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def run_benchmark(dataset: Path, output_dir: Path, counts: list[int]) -> list[dict[str, float]]:
    acquisition = load_picmus_uff(dataset)
    if max(counts) > acquisition.transmit_angles_rad.size:
        raise ValueError("requested more angles than the acquisition contains")
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, float]] = []
    images: dict[int, np.ndarray] = {}
    process = psutil.Process()

    for count in counts:
        gc.collect()
        memory_before = process.memory_info().rss
        start = time.perf_counter()
        result = plane_wave_delay_and_sum(acquisition, angle_count=count)
        runtime = time.perf_counter() - start
        working_set = process.memory_info().rss
        reference = _aligned_reference(acquisition, result.bmode_db.shape)
        metrics = evaluate_similarity(reference, result.bmode_db)
        record = {
            "angle_count": count,
            "runtime_seconds": runtime,
            "frames_per_second": 1.0 / runtime,
            "working_set_mb": working_set / (1024**2),
            "working_set_delta_mb": (working_set - memory_before) / (1024**2),
            "reference_correlation": metrics.correlation,
            "rmse_db": metrics.rmse_db,
            "ssim": metrics.ssim,
            "psnr_db": metrics.psnr_db,
        }
        records.append(record)
        images[count] = result.bmode_db
        if count == 75:
            np.savez_compressed(output_dir / "our_75_angle_bmode_db.npz", bmode_db=result.bmode_db)
        print(json.dumps(record, indent=2))

    (output_dir / "angle_benchmark.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "angle_benchmark.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    _save_reconstruction_grid(acquisition, images, output_dir / "angle_reconstructions.png")
    _save_tradeoff_plot(records, output_dir / "angle_quality_runtime.png")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/raw/PICMUS_carotid_cross.uff"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/benchmark"))
    parser.add_argument("--counts", type=_parse_counts, default=_parse_counts("1,3,11,31,75"))
    args = parser.parse_args()
    run_benchmark(args.dataset, args.output_dir, args.counts)
    print(f"Saved benchmark artifacts to {args.output_dir}")


if __name__ == "__main__":
    main()
