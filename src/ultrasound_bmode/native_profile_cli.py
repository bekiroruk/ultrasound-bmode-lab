"""Matched, isolated-process C++ and Numba analytic linear/cubic profiling."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .accelerated import numba_plane_wave_delay_and_sum
from .native_backend import native_build_info, native_library_path, native_plane_wave_delay_and_sum
from .real_data import load_picmus_uff, plane_wave_delay_and_sum
from .reconstruction_quality_cli import _sha256
from .runtime_profile_cli import profile_call
from .sequence import UFFPlaneWaveSequence


def agreement(actual, expected):
    np.testing.assert_allclose(actual["rf"], expected["rf"], rtol=1e-5, atol=1e-7)
    np.testing.assert_allclose(actual["bmode"], expected["bmode"], rtol=0, atol=1e-4)
    return {
        "rf_max_abs_error": float(np.max(abs(actual["rf"]-expected["rf"]))),
        "bmode_max_abs_error_db": float(np.max(abs(actual["bmode"]-expected["bmode"]))),
        "rf_rtol": 1e-5, "rf_atol": 1e-7, "bmode_atol_db": 1e-4, "passed": True,
    }


def worker(dataset, backend, interpolation, count, repeats, output):
    acquisition = load_picmus_uff(dataset)
    function = native_plane_wave_delay_and_sum if backend == "cpp" else numba_plane_wave_delay_and_sum
    kwargs = {"angle_count": count, "analytic": True, "interpolation": interpolation,
              "angle_batch_size": 8}
    if backend == "cpp":
        kwargs["threads"] = 8
    report, result = profile_call(lambda: function(acquisition, **kwargs), repeats)
    np.savez_compressed(output, rf=result.rf, bmode=result.bmode_db)
    report.update({"backend": backend, "interpolation": interpolation, "angle_count": count,
                   "output_shape": list(result.rf.shape)})
    return report


def run_profile(dataset, sequence_path, output_dir, repeats=5):
    if repeats < 2:
        raise ValueError("repeats must be >= 2")
    root = Path(__file__).resolve().parents[2]
    info = native_build_info()
    info["library"] = Path(info["library"]).name
    info["binary_sha256"] = _sha256(native_library_path())
    report = {
        "dataset": dataset.name, "sha256": _sha256(dataset),
        "platform": platform.platform(), "processor": platform.processor(),
        "python": platform.python_version(), "native_build": info,
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "numba", "psutil")},
        "source_sha256": {name: _sha256(root / name) for name in (
            "native/beamformer.cpp", "native/CMakeLists.txt",
            "src/ultrasound_bmode/native_backend.py", "src/ultrasound_bmode/real_data.py",
            "src/ultrasound_bmode/accelerated.py")},
        "settings": {"threads": 8, "angle_batch_size": 8, "analytic": True,
                     "f_number": 1.5, "strides": [2, 2], "dynamic_range_db": 60, "repeats": repeats},
        "protocol": (
            "Fresh subprocess per backend/interpolation/count, run sequentially. One full warmup "
            "excluded, then five timed full calls by default. Includes channel validation/selection, "
            "Hilbert quadrature, double conversion for C++, focusing and log compression; data load "
            "excluded. Eight Numba/OpenMP threads requested; C++ falls back to serial without OpenMP. "
            "Separate additional call samples process RSS every requested 2 ms; sampled lower bound, "
            "not allocation size. Warmup and retained allocator buffers affect baseline. No analytic "
            "cache. C++ focuses both components; preprocessing remains Python/SciPy. Not a fully "
            "native pipeline, live integration, GPU result, or universal speedup claim. "
            "Fixed process order is not counterbalanced; thermal/scheduler effects remain possible."
        ),
        "records": [], "cpp_numba_agreement": [], "cpp_numpy_agreement": [],
    }
    env = {**os.environ, "NUMBA_NUM_THREADS": "8", "OMP_NUM_THREADS": "8", "MPLBACKEND": "Agg"}
    with tempfile.TemporaryDirectory(prefix="ultrasound-native-") as directory:
        arrays = {}
        for interpolation in ("linear", "cubic"):
            for count in (11, 75):
                for backend in ("numba", "cpp"):
                    key = f"{backend}_{interpolation}_{count}"
                    output = Path(directory) / (key + ".npz")
                    command = [
                        sys.executable, "-m", "ultrasound_bmode.native_profile_cli", "--worker",
                        "--dataset", str(dataset.resolve()), "--backend", backend,
                        "--interpolation", interpolation, "--count", str(count),
                        "--repeats", str(repeats), "--result-path", str(output),
                    ]
                    done = subprocess.run(command, env=env, capture_output=True, text=True,
                                          check=True, timeout=600)
                    row = json.loads(done.stdout)
                    report["records"].append(row)
                    with np.load(output) as data:
                        arrays[key] = {name: data[name] for name in data.files}
                    print(f"{key}: {row['median_seconds']:.4f} s", flush=True)
                comparison = agreement(arrays[f"cpp_{interpolation}_{count}"],
                                       arrays[f"numba_{interpolation}_{count}"])
                report["cpp_numba_agreement"].append(
                    {"interpolation": interpolation, "angle_count": count, **comparison})
        acquisition = load_picmus_uff(dataset)
        for interpolation in ("linear", "cubic"):
            result = plane_wave_delay_and_sum(acquisition, angle_count=11, analytic=True,
                                             interpolation=interpolation)
            report["cpp_numpy_agreement"].append({
                "interpolation": interpolation, "angle_count": 11,
                **agreement(arrays[f"cpp_{interpolation}_11"],
                            {"rf": result.rf, "bmode": result.bmode_db}),
            })
    # A second measured acquisition layout, with nonzero transmit delay.
    report["sequence_dataset"] = {"filename": sequence_path.name, "sha256": _sha256(sequence_path)}
    report["sequence_cpp_numpy_agreement"] = []
    with UFFPlaneWaveSequence(sequence_path) as sequence:
        for index in (0, sequence.frame_count//2, sequence.frame_count-1):
            acquisition = sequence.read_frame(index)
            kwargs = {"angle_count": 1, "analytic": True, "interpolation": "cubic",
                      "lateral_stride": 1, "axial_stride": 1}
            expected = plane_wave_delay_and_sum(acquisition, **kwargs)
            actual = native_plane_wave_delay_and_sum(acquisition, **kwargs)
            report["sequence_cpp_numpy_agreement"].append({
                "frame": index, **agreement({"rf": actual.rf, "bmode": actual.bmode_db},
                                            {"rf": expected.rf, "bmode": expected.bmode_db}),
            })
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n",
                                            encoding="utf-8")
    rows = report["records"]
    lines = ["# C++ analytic focusing: verification and matched profile", "", report["protocol"], "",
             "| Interpolation | Angles | Backend | Median s | Sampled RSS MiB |",
             "|---|---:|---|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['interpolation']} | {row['angle_count']} | {row['backend']} | "
                     f"{row['median_seconds']:.4f} | {row['rss_sampled_peak_mib']:.1f} |")
    lines += ["", "C++/Numba full-array equivalence: all four configurations passed.",
              "C++/NumPy: both 11-angle methods and SWE frames 0/middle/last passed.",
              "RF rtol=1e-5, atol=1e-7; B-mode atol=1e-4 dB; numerical, not clinical equivalence.",
              "", "![Matched profile](profile.png)", "", "[Raw evidence](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    labels = [f"{r['backend']}\n{r['interpolation']}\n{r['angle_count']} angles" for r in rows]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    colors = ["#207b8c" if r["backend"] == "cpp" else "#b6c0cb" for r in rows]
    axes[0].bar(labels, [r["median_seconds"] for r in rows], color=colors)
    axes[0].set(ylabel="Median seconds", title="Warm full calls; 8 threads, batch 8")
    axes[1].bar(labels, [r["rss_sampled_peak_mib"] for r in rows], color=colors)
    axes[1].set(ylabel="Sampled RSS [MiB]", title="Separate memory pass")
    for axis in axes:
        axis.tick_params(axis="x", labelsize=8)
    fig.savefig(output_dir / "profile.png", dpi=160)
    plt.close(fig)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/raw/PICMUS_carotid_cross.uff"))
    parser.add_argument("--sequence", type=Path, default=Path("data/raw/SWE_L7_type_I.uff"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/native_profile"))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--backend", choices=["cpp", "numba"], help=argparse.SUPPRESS)
    parser.add_argument("--interpolation", choices=["linear", "cubic"], help=argparse.SUPPRESS)
    parser.add_argument("--count", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--result-path", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.dataset, args.backend, args.interpolation, args.count,
                                args.repeats, args.result_path)))
    else:
        run_profile(args.dataset, args.sequence, args.output_dir, args.repeats)


if __name__ == "__main__":
    main()
