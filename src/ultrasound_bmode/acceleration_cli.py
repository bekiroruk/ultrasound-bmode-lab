"""Benchmark NumPy and compiled Numba DAS backends on measured RF data."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import matplotlib.pyplot as plt

from .accelerated import cuda_available, numba_plane_wave_delay_and_sum
from .metrics import evaluate_similarity
from .native_backend import native_available
from .real_data import load_picmus_uff, plane_wave_delay_and_sum


def run_acceleration_benchmark(
    dataset: Path,
    output_dir: Path,
    angle_counts: tuple[int, ...] = (1, 11, 75),
) -> dict[str, object]:
    acquisition = load_picmus_uff(dataset)
    output_dir.mkdir(parents=True, exist_ok=True)

    compile_start = time.perf_counter()
    numba_plane_wave_delay_and_sum(
        acquisition, angle_count=1, lateral_stride=1000, axial_stride=1000
    )
    compilation_seconds = time.perf_counter() - compile_start

    records = []
    for count in angle_counts:
        start = time.perf_counter()
        numpy_result = plane_wave_delay_and_sum(acquisition, angle_count=count)
        numpy_seconds = time.perf_counter() - start
        start = time.perf_counter()
        numba_result = numba_plane_wave_delay_and_sum(acquisition, angle_count=count)
        numba_seconds = time.perf_counter() - start
        agreement = evaluate_similarity(numpy_result.bmode_db, numba_result.bmode_db)
        records.append(
            {
                "angle_count": count,
                "numpy_seconds": numpy_seconds,
                "numba_seconds": numba_seconds,
                "speedup": numpy_seconds / numba_seconds,
                "bmode_correlation": agreement.correlation,
                "bmode_rmse_db": agreement.rmse_db,
            }
        )
        print(json.dumps(records[-1], indent=2))

    report = {
        "numba_compilation_seconds_excluded_from_runtime": compilation_seconds,
        "backend_status": {
            "numpy": "available",
            "numba_cpu": "available",
            "numba_cuda": "available" if cuda_available() else "unavailable: no CUDA device",
            "cpp_openmp": (
                "available" if native_available() else "unavailable: optional library not built"
            ),
        },
        "records": records,
    }
    (output_dir / "acceleration_benchmark.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    counts = [record["angle_count"] for record in records]
    numpy_times = [record["numpy_seconds"] for record in records]
    numba_times = [record["numba_seconds"] for record in records]
    positions = list(range(len(counts)))
    fig, axis = plt.subplots(figsize=(7.8, 4.7))
    axis.bar([position - 0.18 for position in positions], numpy_times, 0.36, label="NumPy")
    axis.bar([position + 0.18 for position in positions], numba_times, 0.36, label="Numba")
    axis.set(
        xticks=positions,
        xticklabels=counts,
        xlabel="Compounded plane waves",
        ylabel="Runtime [s]",
        yscale="log",
        title="Measured RF beamforming acceleration",
    )
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "acceleration_benchmark.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/raw/PICMUS_carotid_cross.uff"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/acceleration"))
    args = parser.parse_args()
    report = run_acceleration_benchmark(args.dataset, args.output_dir)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
