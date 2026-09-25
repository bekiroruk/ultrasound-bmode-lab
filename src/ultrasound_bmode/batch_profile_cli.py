"""Measure batched 75-angle analytic CPWC in isolated sequential subprocesses."""

from __future__ import annotations

import argparse
import json
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


def run_batch_profile(dataset: Path, output_dir: Path, repeats=3):
    if repeats < 2:
        raise ValueError("at least two repeats are required")
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "dataset": dataset.name, "sha256": _sha256(dataset),
        "platform": platform.platform(), "processor": platform.processor(),
        "logical_cpus": psutil.cpu_count(), "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "numba", "psutil")},
        "settings": {"angles": 75, "stride": 2, "analytic": True, "repeats": repeats},
        "protocol": (
            "Fresh sequential subprocess for each F-number/batch configuration. One full warmup, "
            "then repeated timed calls; RSS sampling in a separate additional call. Includes "
            "channel preparation, analytic transformation, beamforming and log compression. "
            "Excludes loading, warmup/JIT/cache startup, saving and plotting."
        ),
        "limitations": (
            "Input RF remains resident: angle batching is not disk/device streaming. RSS includes "
            "interpreter, libraries, input and retained buffers; sampled peak is a lower bound, "
            "not total allocated bytes. Single-host measurements, not real-time certification. "
            "F/0.8 is still exploratory; timing does not validate its image quality."
        ),
        "records": [],
    }
    with tempfile.TemporaryDirectory(prefix="ultrasound-batch-profile-") as directory:
        root = Path(directory)
        for f_number, batches in ((1.5, (None, 8, 16, 32)), (0.8, (None, 16))):
            reference_path = None
            for batch in batches:
                path = root / f"f{f_number}_b{batch}.npz"
                command = [sys.executable, "-m", "ultrasound_bmode.runtime_profile_cli", "--worker",
                           "--dataset", str(dataset.resolve()), "--backend", "numba", "--analytic",
                           "--count", "75", "--repeats", str(repeats), "--f-number", str(f_number),
                           "--result-path", str(path)]
                if batch is not None:
                    command += ["--angle-batch-size", str(batch)]
                completed = run_process(command, capture_output=True, text=True, check=True,
                                        timeout=600)
                row = json.loads(completed.stdout)
                row["parity_to_same_f_number_unbatched"] = None
                if batch is None:
                    reference_path = path
                else:
                    with np.load(reference_path) as reference, np.load(path) as actual:
                        np.testing.assert_allclose(actual["rf"], reference["rf"], rtol=1e-5, atol=1e-7)
                        np.testing.assert_allclose(actual["bmode"], reference["bmode"], rtol=0, atol=1e-4)
                        row["parity_to_same_f_number_unbatched"] = {
                            "passed": True,
                            "rf_max_absolute_error": float(np.max(np.abs(actual["rf"] - reference["rf"]))),
                            "bmode_max_absolute_error_db": float(np.max(np.abs(actual["bmode"] - reference["bmode"]))),
                        }
                report["records"].append(row)
                print(f"F/{f_number}, batch={batch}: {row['median_seconds']:.3f} s, "
                      f"{row['rss_sampled_peak_mib']:.1f} MiB sampled RSS peak", flush=True)
    lines = ["# Angle-batched analytic CPWC profile", "", report["protocol"], "",
             report["limitations"], "",
             "| F-number | Angle batch | Median s | Min–max s | FPS | Baseline / peak RSS MiB |",
             "|---:|---|---:|---:|---:|---:|"]
    for row in report["records"]:
        lines.append(f"| {row['f_number']} | {row['angle_batch_size'] or 'All 75'} | "
                     f"{row['median_seconds']:.3f} | {row['minimum_seconds']:.3f}–{row['maximum_seconds']:.3f} "
                     f"| {row['median_fps']:.2f} | {row['rss_baseline_mib']:.1f} / "
                     f"{row['rss_sampled_peak_mib']:.1f} |")
    lines += ["", "Every batched full RF/B-mode array passed comparison to the unbatched result at the same F-number.",
              "", "![Time and working set](batch_profile.png)", "",
              "[Raw repetitions, host, settings and parity errors](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    rows = report["records"]
    labels = [f"F/{row['f_number']}\nbatch {row['angle_batch_size'] or 'all'}" for row in rows]
    colors = ["#8c94a4" if row["angle_batch_size"] is None else "#248c9e" for row in rows]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    axes[0].bar(labels, [row["median_seconds"] for row in rows], color=colors)
    axes[0].set(title="75-angle analytic reconstruction", ylabel="Median seconds")
    axes[1].bar(labels, [row["rss_sampled_peak_mib"] for row in rows], color=colors)
    axes[1].set(title="Separate memory pass", ylabel="Sampled process RSS peak [MiB]")
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    fig.savefig(output_dir / "batch_profile.png", dpi=170)
    plt.close(fig)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/raw/PICMUS_carotid_cross.uff"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/batch_profile"))
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    run_batch_profile(args.dataset, args.output_dir, args.repeats)


if __name__ == "__main__":
    main()
