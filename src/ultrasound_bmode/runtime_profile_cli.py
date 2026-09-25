"""Isolated-process runtime and sampled working-set profiles of measured RF CPWC."""

from __future__ import annotations

import argparse
import gc
import json
import platform
import subprocess
import sys
import tempfile
import threading
import time
from importlib.metadata import version
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import psutil

from .accelerated import numba_plane_wave_delay_and_sum, prepare_analytic_channel_cache
from .real_data import load_picmus_uff, plane_wave_delay_and_sum
from .reconstruction_quality_cli import _sha256


def profile_call(function, repeats=3, sample_interval_s=0.002):
    """Time warm calls without a sampler, then sample RSS in a separate additional call."""
    if repeats < 2 or sample_interval_s <= 0:
        raise ValueError("at least two repeats and a positive sampling interval are required")
    start = time.perf_counter()
    result = function()
    warmup_seconds = time.perf_counter() - start
    durations = []
    for _ in range(repeats):
        result = None
        gc.collect()
        start = time.perf_counter()
        result = function()
        durations.append(time.perf_counter() - start)
    result = None
    gc.collect()
    process = psutil.Process()
    baseline = process.memory_info().rss
    samples = [baseline]
    stop = threading.Event()

    def sample():
        while not stop.wait(sample_interval_s):
            samples.append(process.memory_info().rss)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        result = function()
        samples.append(process.memory_info().rss)
    finally:
        stop.set()
        sampler.join()
    peak = max(samples)
    return {
        "warmup_full_call_seconds_excluded": warmup_seconds,
        "timed_seconds": durations,
        "median_seconds": float(np.median(durations)),
        "minimum_seconds": min(durations), "maximum_seconds": max(durations),
        "median_fps": 1 / float(np.median(durations)),
        "rss_baseline_mib": baseline / 2**20, "rss_sampled_peak_mib": peak / 2**20,
        "rss_peak_above_baseline_mib": (peak - baseline) / 2**20,
        "rss_sample_count": len(samples), "rss_requested_interval_seconds": sample_interval_s,
    }, result


def worker(
    dataset, backend, analytic, count, repeats, output, batch_size=None, f_number=1.5,
    use_analytic_cache=False, cache_batch_size=8,
):
    if backend == "numpy" and batch_size is not None:
        raise ValueError("angle batching is available only for the Numba backend")
    acquisition = load_picmus_uff(dataset)
    reconstruct = numba_plane_wave_delay_and_sum if backend == "numba" else plane_wave_delay_and_sum
    if use_analytic_cache and (backend != "numba" or not analytic):
        raise ValueError("analytic cache profiling requires the analytic Numba backend")
    cache = (
        prepare_analytic_channel_cache(acquisition, cache_batch_size)
        if use_analytic_cache else None
    )
    kwargs = {"angle_count": count, "analytic": analytic, "f_number": f_number}
    if backend == "numba":
        kwargs["angle_batch_size"] = batch_size
        kwargs["analytic_cache"] = cache
    report, result = profile_call(lambda: reconstruct(acquisition, **kwargs), repeats)
    np.savez_compressed(output, rf=result.rf, bmode=result.bmode_db)
    from numba import get_num_threads

    report.update({
        "backend": backend, "mode": "analytic" if analytic else "legacy", "angle_count": count,
        "angle_indices": result.angle_indices.tolist(), "output_shape": list(result.rf.shape),
        "rf_dtype": str(result.rf.dtype), "numba_threads": get_num_threads(),
        "input_channel_mib": acquisition.channel_data.nbytes / 2**20,
        "angle_batch_size": batch_size, "f_number": f_number,
        "analytic_cache": use_analytic_cache,
        "analytic_cache_mib": cache.size_mib if cache is not None else 0.0,
        "analytic_cache_preparation_seconds": (
            cache.preparation_seconds if cache is not None else None
        ),
        "analytic_cache_preparation_batch_size": (
            cache.preparation_batch_size if cache is not None else None
        ),
    })
    return report


def run_runtime_profile(dataset: Path, output_dir: Path, repeats=3):
    if repeats < 2:
        raise ValueError("repeats must be at least two")
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "dataset": dataset.name, "sha256": _sha256(dataset),
        "platform": platform.platform(), "processor": platform.processor(),
        "logical_cpus": psutil.cpu_count(), "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "numba", "psutil")},
        "settings": {"f_number": 1.5, "lateral_stride": 2, "axial_stride": 2,
                     "dynamic_range_db": 60, "repeats": repeats},
        "protocol": (
            "One fresh subprocess per backend/mode/angle combination, executed sequentially. "
            "Load data, run one full warmup, then time repeated full reconstruction calls. "
            "RSS sampling occurs only during a separate extra call, not the timed calls. "
            "Calls include channel selection, Hilbert (when used), beamforming and compression. "
            "File loading, plots, serialization and full warmup are excluded. Warmup may "
            "include JIT/cache loading; it is not a pure compilation-time measurement."
        ),
        "memory_limit": (
            "Sampled process RSS is a lower bound on peak working set, not allocated bytes. "
            "Baseline includes resident data, interpreter, libraries and retained warmup buffers. "
            "Peak-minus-baseline may be small because allocator buffers are reused. "
            "Requested 2 ms sampling is not guaranteed by the scheduler. No GPU/native measurements."
        ),
        "scope": "Single-host research timing; not real-time or clinical certification. NumPy 75 angles not timed.",
        "records": [], "numpy_numba_agreement": [],
    }
    with tempfile.TemporaryDirectory(prefix="ultrasound-profile-") as directory:
        root = Path(directory)
        arrays = {}
        configurations = [(backend, analytic, count)
                          for backend, counts in (("numba", (11, 75)), ("numpy", (11,)))
                          for count in counts for analytic in (False, True)]
        for backend, analytic, count in configurations:
            key = f"{backend}_{'analytic' if analytic else 'legacy'}_{count}"
            output = root / f"{key}.npz"
            command = [sys.executable, "-m", "ultrasound_bmode.runtime_profile_cli", "--worker",
                       "--dataset", str(dataset.resolve()), "--backend", backend,
                       "--count", str(count), "--repeats", str(repeats), "--result-path", str(output)]
            if analytic:
                command.append("--analytic")
            completed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=600)
            row = json.loads(completed.stdout)
            report["records"].append(row)
            arrays[key] = output
            print(f"{key}: {row['median_seconds']:.3f} s; sampled RSS peak "
                  f"{row['rss_sampled_peak_mib']:.1f} MiB", flush=True)
        for mode in ("legacy", "analytic"):
            with np.load(arrays[f"numpy_{mode}_11"]) as expected, \
                 np.load(arrays[f"numba_{mode}_11"]) as actual:
                np.testing.assert_allclose(actual["rf"], expected["rf"], rtol=1e-5, atol=1e-7)
                np.testing.assert_allclose(actual["bmode"], expected["bmode"], atol=1e-4)
                report["numpy_numba_agreement"].append({
                    "mode": mode, "angle_count": 11,
                    "rf_max_absolute_error": float(np.max(np.abs(actual["rf"] - expected["rf"]))),
                    "bmode_max_absolute_error_db": float(np.max(np.abs(actual["bmode"] - expected["bmode"]))),
                    "rf_tolerance": {"rtol": 1e-5, "atol": 1e-7}, "passed": True,
                })
    _save_report(report, output_dir)
    return report


def _save_report(report, output_dir):
    lines = ["# Analytic runtime and memory profile", "", report["protocol"], "",
             report["memory_limit"], "", report["scope"], "",
             "| Backend | Mode | Angles | Median s | Min–max s | FPS | RSS baseline / sampled peak MiB |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for row in report["records"]:
        lines.append(f"| {row['backend']} | {row['mode']} | {row['angle_count']} | "
                     f"{row['median_seconds']:.3f} | {row['minimum_seconds']:.3f}–{row['maximum_seconds']:.3f} "
                     f"| {row['median_fps']:.2f} | {row['rss_baseline_mib']:.1f} / "
                     f"{row['rss_sampled_peak_mib']:.1f} |")
    lines += ["", "Full-array NumPy/Numba numerical agreement passed at 11 angles for both modes.",
              "", "![Runtime and sampled working set](runtime_memory.png)", "",
              "[Raw repeats, host, settings, checksums and agreement errors](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    rows = report["records"]
    labels = [f"{row['backend']}\n{row['mode']}\n{row['angle_count']} angles" for row in rows]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    colors = ["#248c9e" if row["mode"] == "analytic" else "#8c94a4" for row in rows]
    axes[0].bar(labels, [row["median_seconds"] for row in rows], color=colors)
    axes[0].set(ylabel="Median seconds (log scale)", yscale="log", title="Warm full reconstruction")
    axes[1].bar(labels, [row["rss_sampled_peak_mib"] for row in rows], color=colors)
    axes[1].set(ylabel="Sampled process RSS peak [MiB]", title="Separate memory pass; not allocated bytes")
    for axis in axes:
        axis.tick_params(axis="x", labelsize=8)
        axis.grid(axis="y", alpha=0.2)
    fig.savefig(output_dir / "runtime_memory.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/raw/PICMUS_carotid_cross.uff"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/runtime_profile"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--backend", choices=["numpy", "numba"], default="numba", help=argparse.SUPPRESS)
    parser.add_argument("--count", type=int, default=11, help=argparse.SUPPRESS)
    parser.add_argument("--analytic", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--result-path", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--angle-batch-size", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--f-number", type=float, default=1.5, help=argparse.SUPPRESS)
    parser.add_argument("--use-analytic-cache", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cache-batch-size", type=int, default=8, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        if args.result_path is None:
            parser.error("--worker requires --result-path")
        print(json.dumps(worker(args.dataset, args.backend, args.analytic, args.count,
                                args.repeats, args.result_path, args.angle_batch_size, args.f_number,
                                args.use_analytic_cache, args.cache_batch_size)))
    else:
        run_runtime_profile(args.dataset, args.output_dir, args.repeats)


if __name__ == "__main__":
    main()
