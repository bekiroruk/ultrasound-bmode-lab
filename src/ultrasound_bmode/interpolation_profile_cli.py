"""Measure linear/cubic CPWC cost with matched settings and reversed process order."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from numbers import Integral
from pathlib import Path
from subprocess import run as run_process

import matplotlib.pyplot as plt
import numpy as np
import psutil

from .reconstruction_quality_cli import _sha256


def _check_repeat(reference_path, actual_path):
    with np.load(reference_path) as reference, np.load(actual_path) as actual:
        for name in ("x_axis_m", "z_axis_m", "angle_indices"):
            np.testing.assert_array_equal(actual[name], reference[name])
        np.testing.assert_allclose(actual["rf"], reference["rf"], rtol=1e-5, atol=1e-7)
        np.testing.assert_allclose(actual["bmode"], reference["bmode"], rtol=0, atol=1e-4)
        return {"passed": True, "rf_max_absolute_error": float(
            np.max(np.abs(actual["rf"] - reference["rf"]))
        ), "bmode_max_absolute_error_db": float(
            np.max(np.abs(actual["bmode"] - reference["bmode"]))
        )}


def _summarize(records):
    summaries = []
    for count in (11, 75):
        for method in ("linear", "cubic"):
            rows = [row for row in records
                    if row["angle_count"] == count and row["interpolation"] == method]
            durations = [value for row in rows for value in row["timed_seconds"]]
            median = float(np.median(durations))
            summaries.append({
                "angle_count": count, "interpolation": method,
                "timed_call_count": len(durations), "process_count": len(rows),
                "median_seconds": median, "minimum_seconds": min(durations),
                "maximum_seconds": max(durations), "median_fps": 1 / median,
                "maximum_sampled_rss_peak_mib": max(row["rss_sampled_peak_mib"] for row in rows),
            })
    comparisons = []
    for count in (11, 75):
        linear, cubic = [row for row in summaries if row["angle_count"] == count]
        comparisons.append({
            "angle_count": count,
            "cubic_time_increase_percent": (
                100 * (cubic["median_seconds"] / linear["median_seconds"] - 1)
            ),
            "cubic_peak_rss_increase_mib": (
                cubic["maximum_sampled_rss_peak_mib"] - linear["maximum_sampled_rss_peak_mib"]
            ),
        })
    return summaries, comparisons


def run_interpolation_profile(dataset: Path, output_dir: Path, repeats=5, threads=8):
    if isinstance(repeats, bool) or not isinstance(repeats, Integral) or repeats < 2:
        raise ValueError("repeats must be an integer of at least two")
    if isinstance(threads, bool) or not isinstance(threads, Integral) or threads < 1:
        raise ValueError("threads must be a positive integer")
    report = {
        "study": "Matched linear/cubic analytic CPWC timing and sampled process memory",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset.name, "sha256": _sha256(dataset),
        "platform": platform.platform(), "processor": platform.processor(),
        "logical_cpus": psutil.cpu_count(), "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "numba", "psutil")},
        "settings": {"analytic": True, "f_number": 1.7, "stride": 2,
                     "dynamic_range_db": 60, "angle_batch_size": 8,
                     "analytic_cache": True, "cache_batch_size": 8,
                     "numba_threads": int(threads), "timed_repeats_per_process": int(repeats),
                     "rounds": 2},
        "protocol": (
            "Two rounds of fresh sequential subprocesses. Round 1 runs 11-linear, 11-cubic, "
            "75-linear, 75-cubic; round 2 reverses this order. Each process loads the same RF, "
            "prepares the full analytic cache, excludes one full warmup, times repeated calls "
            "without a memory sampler, then samples RSS during a separate additional call. "
            "The reported median pools both rounds. No benchmark runs concurrently."
        ),
        "limitations": (
            "Single host, repeated reconstruction of one loaded acquisition. Preparation, "
            "loading, warmup, plotting and serialization are excluded from timings; raw "
            "preparation/warmup times remain in JSON. Peak RSS includes cached channels and "
            "is a sampled lower bound. OS load, scheduling and CPU power are not controlled. "
            "These are reconstruction timings, not acquisition-to-display or sustained cine FPS."
        ),
        "parity_policy": (
            "Compare repeat outputs only within the SAME interpolation method and angle count. "
            "Linear and cubic deliberately differ; only their coordinates and angle indices "
            "must match. Quality evidence lives in the separate transfer and phantom reports."
        ),
        "records": [], "repeat_parity": [],
    }
    configurations = [(count, method) for count in (11, 75) for method in ("linear", "cubic")]
    environment = os.environ.copy()
    environment["NUMBA_NUM_THREADS"] = str(threads)
    environment["MPLBACKEND"] = "Agg"
    with tempfile.TemporaryDirectory(prefix="ultrasound-interpolation-profile-") as directory:
        root = Path(directory)
        first_outputs = {}
        for round_index, order in enumerate((configurations, configurations[::-1]), start=1):
            for count, method in order:
                path = root / f"round{round_index}_{count}_{method}.npz"
                command = [
                    sys.executable, "-m", "ultrasound_bmode.runtime_profile_cli", "--worker",
                    "--dataset", str(dataset.resolve()), "--backend", "numba", "--analytic",
                    "--count", str(count), "--repeats", str(repeats), "--f-number", "1.7",
                    "--angle-batch-size", "8", "--use-analytic-cache", "--cache-batch-size", "8",
                    "--interpolation", method, "--result-path", str(path),
                ]
                completed = run_process(command, env=environment, capture_output=True, text=True,
                                        check=True, timeout=600)
                row = json.loads(completed.stdout)
                if (row["interpolation"] != method or row["angle_count"] != count
                        or row["numba_threads"] != threads):
                    raise ValueError("worker returned a different profile configuration")
                row["round"] = round_index
                report["records"].append(row)
                key = (count, method)
                if key not in first_outputs:
                    first_outputs[key] = path
                else:
                    report["repeat_parity"].append({
                        "angle_count": count, "interpolation": method,
                        **_check_repeat(first_outputs[key], path),
                    })
                print(f"Round {round_index}, {count} angles, {method}: "
                      f"{row['median_seconds']:.3f} s, "
                      f"{row['rss_sampled_peak_mib']:.1f} MiB RSS", flush=True)
        for count in (11, 75):
            with np.load(first_outputs[(count, "linear")]) as linear, \
                 np.load(first_outputs[(count, "cubic")]) as cubic:
                for name in ("x_axis_m", "z_axis_m", "angle_indices"):
                    np.testing.assert_array_equal(linear[name], cubic[name])
    report["summaries"], report["comparisons"] = _summarize(report["records"])
    output_dir.mkdir(parents=True, exist_ok=True)
    _save_report(report, output_dir)
    return report


def _save_report(report, output_dir):
    lines = ["# Linear/cubic reconstruction performance", "", report["protocol"], "",
             report["limitations"], "", report["parity_policy"], "",
             (f"F/1.7, stride 2, batch 8, cached analytic channels; "
              f"{report['settings']['numba_threads']} Numba threads."), "",
             "| Angles | Method | Median s | Min–max s | FPS | Maximum sampled RSS MiB |",
             "|---:|---|---:|---:|---:|---:|"]
    for row in report["summaries"]:
        lines.append(f"| {row['angle_count']} | {row['interpolation']} | "
                     f"{row['median_seconds']:.3f} | {row['minimum_seconds']:.3f}–"
                     f"{row['maximum_seconds']:.3f} | {row['median_fps']:.2f} | "
                     f"{row['maximum_sampled_rss_peak_mib']:.1f} |")
    for row in report["comparisons"]:
        lines += ["", (f"{row['angle_count']} angles: cubic duration changed by "
                       f"{row['cubic_time_increase_percent']:+.1f}%; sampled peak RSS by "
                       f"{row['cubic_peak_rss_increase_mib']:+.1f} MiB.")]
    lines += ["", "All four same-method/angle-count repeat RF/B-mode comparisons passed.", "",
              "![Runtime and sampled process memory](interpolation_profile.png)", "",
              "[All durations, process settings, preparation cost and parity errors](metrics.json)",
              ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    rows = report["summaries"]
    labels = [f"{row['angle_count']} angles\n{row['interpolation']}" for row in rows]
    colors = ["#248c9e" if row["interpolation"] == "cubic" else "#8c94a4" for row in rows]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.5), layout="constrained")
    axes[0].bar(labels, [row["median_seconds"] for row in rows], color=colors)
    axes[0].set(title="Two process orders; pooled warm calls", ylabel="Median seconds")
    axes[1].bar(labels, [row["maximum_sampled_rss_peak_mib"] for row in rows], color=colors)
    axes[1].set(title="Separate RSS passes", ylabel="Maximum sampled process RSS [MiB]")
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    fig.savefig(output_dir / "interpolation_profile.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/raw/PICMUS_carotid_cross.uff"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/interpolation_profile"))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    run_interpolation_profile(args.dataset, args.output_dir, args.repeats, args.threads)


if __name__ == "__main__":
    main()
