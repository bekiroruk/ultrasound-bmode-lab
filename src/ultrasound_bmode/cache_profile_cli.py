"""Profile reusable channel-quadrature cache on repeated measured-RF reconstruction."""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from subprocess import run as run_process

import matplotlib.pyplot as plt
import numpy as np
import psutil

from .reconstruction_quality_cli import _sha256


def run_cache_profile(dataset: Path, output_dir: Path, repeats=3):
    if repeats < 2:
        raise ValueError("at least two repeats are required")
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "dataset": dataset.name, "sha256": _sha256(dataset),
        "platform": platform.platform(), "processor": platform.processor(),
        "logical_cpus": psutil.cpu_count(), "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "numba", "psutil")},
        "settings": {"f_number": 1.5, "stride": 2, "analytic": True,
                     "angle_batch_size": 8, "cache_preparation_batch_size": 8,
                     "repeats": repeats},
        "protocol": (
            "Fresh sequential subprocess for each cached/uncached angle-count configuration. "
            "Cache preparation occurs once after loading and before reconstruction profiling. "
            "Each profile excludes one full warmup, times repeated reconstruction calls without "
            "RSS sampling, then samples RSS during a separate extra call. Cache preparation time "
            "is measured but its temporary peak RSS is not sampled."
        ),
        "limitations": (
            "The in-memory cache stores one full real quadrature tensor and assumes its exact "
            "source channel array is not mutated. Cached RSS includes that resident tensor. "
            "This optimizes repeated reconstructions of one loaded acquisition; it does not "
            "reduce first-use latency, raw input residency, or provide persistent disk caching. "
            "Single-host research measurements, not real-time certification."
        ),
        "records": [], "comparisons": [], "parity": [],
    }
    with tempfile.TemporaryDirectory(prefix="ultrasound-cache-profile-") as directory:
        root = Path(directory)
        arrays = {}
        for count in (11, 75):
            for cached in (False, True):
                key = f"{count}_{'cached' if cached else 'uncached'}"
                output = root / f"{key}.npz"
                command = [
                    sys.executable, "-m", "ultrasound_bmode.runtime_profile_cli", "--worker",
                    "--dataset", str(dataset.resolve()), "--backend", "numba", "--analytic",
                    "--count", str(count), "--repeats", str(repeats), "--f-number", "1.5",
                    "--angle-batch-size", "8", "--cache-batch-size", "8",
                    "--result-path", str(output),
                ]
                if cached:
                    command.append("--use-analytic-cache")
                completed = run_process(command, capture_output=True, text=True, check=True,
                                        timeout=600)
                row = json.loads(completed.stdout)
                report["records"].append(row)
                arrays[key] = output
                print(f"{count} angles, {key.split('_')[1]}: {row['median_seconds']:.3f} s; "
                      f"RSS {row['rss_sampled_peak_mib']:.1f} MiB", flush=True)
            with np.load(arrays[f"{count}_uncached"]) as expected, \
                 np.load(arrays[f"{count}_cached"]) as actual:
                np.testing.assert_allclose(actual["rf"], expected["rf"], rtol=1e-5, atol=1e-7)
                np.testing.assert_allclose(actual["bmode"], expected["bmode"], rtol=0, atol=1e-4)
                report["parity"].append({
                    "angle_count": count, "passed": True,
                    "rf_max_absolute_error": float(np.max(np.abs(actual["rf"] - expected["rf"]))),
                    "bmode_max_absolute_error_db": float(
                        np.max(np.abs(actual["bmode"] - expected["bmode"]))
                    ),
                })
            uncached = report["records"][-2]
            cached = report["records"][-1]
            saving = uncached["median_seconds"] - cached["median_seconds"]
            preparation = cached["analytic_cache_preparation_seconds"]
            report["comparisons"].append({
                "angle_count": count,
                "median_seconds_saved_per_call": saving,
                "repeated_call_time_reduction_percent": (
                    100 * saving / uncached["median_seconds"]
                ),
                "sampled_peak_rss_increase_mib": (
                    cached["rss_sampled_peak_mib"] - uncached["rss_sampled_peak_mib"]
                ),
                "break_even_reconstruction_count": (
                    math.floor(preparation / saving) + 1 if saving > 0 else None
                ),
            })
    _save_report(report, output_dir)
    return report


def _save_report(report, output_dir):
    lines = ["# Reusable analytic-channel cache profile", "", report["protocol"], "",
             report["limitations"], "",
             "| Angles | Cache | Median s | Min–max s | RSS baseline / peak MiB | Cache prep s / MiB |",
             "|---:|---|---:|---:|---:|---:|"]
    for row in report["records"]:
        preparation = (f"{row['analytic_cache_preparation_seconds']:.3f} / "
                       f"{row['analytic_cache_mib']:.1f}"
                       if row["analytic_cache"] else "N/A")
        lines.append(f"| {row['angle_count']} | {'yes' if row['analytic_cache'] else 'no'} | "
                     f"{row['median_seconds']:.3f} | {row['minimum_seconds']:.3f}–"
                     f"{row['maximum_seconds']:.3f} | {row['rss_baseline_mib']:.1f} / "
                     f"{row['rss_sampled_peak_mib']:.1f} | {preparation} |")
    lines += ["", "| Angles | Repeated-call reduction | RSS peak increase | Break-even calls |",
              "|---:|---:|---:|---:|"]
    for row in report["comparisons"]:
        break_even = (str(row["break_even_reconstruction_count"])
                      if row["break_even_reconstruction_count"] is not None else "not reached")
        lines.append(f"| {row['angle_count']} | "
                     f"{row['repeated_call_time_reduction_percent']:.1f}% | "
                     f"{row['sampled_peak_rss_increase_mib']:.1f} MiB | {break_even} |")
    lines += ["", ("Break-even includes the one-time cache preparation measurement, but excludes "
                   "file loading and compilation. It is specific to this run and host."), "",
              "Cached and uncached full RF/B-mode arrays passed at both angle counts.", "",
              "![Repeated reconstruction runtime and working set](cache_profile.png)", "",
              "[Raw repetitions, preparation cost, host and parity errors](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    rows = report["records"]
    labels = [f"{row['angle_count']} angles\n{'cached' if row['analytic_cache'] else 'uncached'}"
              for row in rows]
    colors = ["#248c9e" if row["analytic_cache"] else "#8c94a4" for row in rows]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.6), layout="constrained")
    axes[0].bar(labels, [row["median_seconds"] for row in rows], color=colors)
    axes[0].set(title="Repeated analytic reconstruction", ylabel="Median seconds")
    axes[1].bar(labels, [row["rss_sampled_peak_mib"] for row in rows], color=colors)
    axes[1].set(title="Separate memory pass", ylabel="Sampled process RSS peak [MiB]")
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    fig.savefig(output_dir / "cache_profile.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/raw/PICMUS_carotid_cross.uff"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/cache_profile"))
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    run_cache_profile(args.dataset, args.output_dir, args.repeats)


if __name__ == "__main__":
    main()
