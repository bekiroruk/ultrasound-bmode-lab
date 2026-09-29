"""Process a measured RF sequence in storage order with bounded frame buffers."""

from __future__ import annotations

import argparse
import json
import platform
import time
from importlib.metadata import version
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import psutil

from .accelerated import numba_plane_wave_delay_and_sum
from .real_data import plane_wave_delay_and_sum
from .reconstruction_quality_cli import _sha256
from .sequence import UFFPlaneWaveSequence


def run_sequence(dataset, output_dir):
    from numba import get_num_threads

    process = psutil.Process()
    kwargs = {"angle_count": 1, "lateral_stride": 1, "axial_stride": 1,
              "analytic": True, "interpolation": "cubic", "f_number": 1.5}
    frames, timings, rss, checks = {}, [], [], []
    with UFFPlaneWaveSequence(dataset) as sequence:
        # Warm JIT/allocators without retaining the result or reusing quadrature across frames.
        warm_start = time.perf_counter()
        numba_plane_wave_delay_and_sum(sequence.read_frame(0), **kwargs)
        warm_seconds = time.perf_counter() - warm_start
        baseline = process.memory_info().rss / 2**20
        checkpoints = set(np.linspace(0, sequence.frame_count - 1, 5, dtype=int).tolist())
        validation_frames = {0, sequence.frame_count // 2, sequence.frame_count - 1}
        for index in range(sequence.frame_count):
            start = time.perf_counter()
            acquisition = sequence.read_frame(index)
            result = numba_plane_wave_delay_and_sum(acquisition, **kwargs)
            timings.append(time.perf_counter() - start)
            rss.append(process.memory_info().rss / 2**20)
            if index in checkpoints:
                frames[index] = result.bmode_db.copy()
            del result, acquisition
            if (index+1) % 25 == 0:
                print(f"{index+1}/{sequence.frame_count} frames processed", flush=True)
        # Reference validation is a separate pass, not an interruption of playback.
        for index in sorted(validation_frames):
            acquisition = sequence.read_frame(index)
            result = numba_plane_wave_delay_and_sum(acquisition, **kwargs)
            reference = plane_wave_delay_and_sum(acquisition, **kwargs)
            np.testing.assert_allclose(result.rf, reference.rf, rtol=1e-5, atol=1e-7)
            np.testing.assert_allclose(result.bmode_db, reference.bmode_db, rtol=0, atol=1e-4)
            checks.append({
                "frame": index, "rf_max_abs_error": float(np.max(abs(result.rf-reference.rf))),
                "bmode_max_abs_error_db": float(np.max(abs(result.bmode_db-reference.bmode_db))),
                "passed": True,
            })
            del result, reference, acquisition
        ms = np.asarray(timings) * 1000
        report = {
            "dataset": Path(dataset).name, "sha256": _sha256(dataset),
            "source": "https://zenodo.org/records/20261898",
            "specimen": "not established; do not label this sequence as patient data",
            "platform": platform.platform(), "python": platform.python_version(),
            "dependencies": {name: version(name) for name in ("numpy", "scipy", "numba", "h5py")},
            "numba_threads": get_num_threads(), "backend": "numba", "settings": kwargs,
            "input_shape": list(sequence.shape), "input_dtype": str(sequence.dtype),
            "frame_count": sequence.frame_count, "output_shape": [sequence.z.size, sequence.x.size],
            "x_extent_mm": (sequence.x[[0, -1]]*1000).tolist(),
            "z_extent_mm": (sequence.z[[0, -1]]*1000).tolist(),
            "sampling_frequency_hz": sequence.fs, "sound_speed_m_s": sequence.c,
            "channel_initial_time_s": sequence.initial_time, "wave_delay_s": sequence.wave_delay,
            "effective_initial_time_s": sequence.effective_initial_time_s,
            "transmit_angle_rad": sequence.angle, "acquisition_frame_rate_hz": None,
            "warmup_seconds_excluded": warm_seconds,
            "latency_ms": ms.tolist(), "median_ms": float(np.median(ms)),
            "p95_ms": float(np.percentile(ms, 95)), "maximum_ms": float(max(ms)),
            "processing_fps": len(timings)/sum(timings),
            "rss_baseline_mib": baseline, "rss_post_frame_mib": rss,
            "rss_post_frame_max_mib": max(rss),
            "rss_last25_minus_first25_mean_mib": float(np.mean(rss[-25:])-np.mean(rss[:25])),
            "raw_frame_mib": float(np.prod(sequence.shape[1:])*sequence.dtype.itemsize/2**20),
            "numpy_checkpoint_agreement": checks,
            "protocol": (
                "Sequential offline file playback, not live device ingestion. One RF frame at a "
                "time; no queue, no cross-frame analytic cache. Warmup excluded. Timings include "
                "HDF5 read, finite-value validation, per-frame Hilbert, focusing and compression. "
                "NumPy verification is a separate pass; retaining five previews is untimed; "
                "processing FPS is sum-of-timed-work throughput, not end-to-end wall throughput. "
                "RSS sampled after each frame (not transient peak); includes retained previews and "
                "allocator buffers. Storage cache state is uncontrolled. No frame period is given "
                "by the file; no deadlines, sustained device throughput or clinical claims."
            ),
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n",
                                            encoding="utf-8")
    fig, axes = plt.subplots(1, len(frames), figsize=(15, 5), layout="constrained")
    for axis, (index, pixels) in zip(axes, frames.items(), strict=True):
        axis.imshow(pixels, cmap="gray", vmin=-60, vmax=0,
                    extent=[*report["x_extent_mm"], *report["z_extent_mm"][::-1]],
                    aspect="equal")
        axis.set(title=f"Measured RF frame {index}", xlabel="Lateral [mm]", ylabel="Depth [mm]")
    fig.suptitle("SWE L7 sequence — specimen unspecified; analytic cubic DAS; 60 dB")
    fig.savefig(output_dir / "frames.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), layout="constrained", sharex=True)
    axes[0].plot(ms)
    axes[0].set(ylabel="Processing latency [ms]", title="Offline measured RF playback")
    axes[1].plot(rss)
    axes[1].set(ylabel="Post-frame RSS [MiB]", xlabel="Stored frame index")
    fig.savefig(output_dir / "profile.png", dpi=160)
    plt.close(fig)
    lines = [
        "# Measured RF sequence playback", "", report["protocol"], "",
        f"Source: [USTB archive]({report['source']}); specimen unspecified (not claimed patient data).",
        f"SHA256: `{report['sha256']}`.", "",
        f"- {report['frame_count']} stored RF frames; input {report['input_shape']}.",
        f"- {report['output_shape']} pixels, analytic cubic DAS, {report['numba_threads']} CPU threads.",
        (f"- Median {report['median_ms']:.2f} ms; p95 {report['p95_ms']:.2f} ms; "
         f"maximum {report['maximum_ms']:.2f} ms; timed-work throughput {report['processing_fps']:.2f} fps."),
        (f"- Post-frame RSS maximum {max(rss):.2f} MiB; last25−first25 mean "
         f"{report['rss_last25_minus_first25_mean_mib']:+.2f} MiB. This does not prove absence of leaks."),
        (f"- NumPy equivalence passed on frames {sorted(validation_frames)}, RF rtol=1e-5/atol=1e-7; "
         "B-mode absolute tolerance 1e-4 dB. Numerical agreement is not image-quality ground truth."),
        "- Effective initial time = channel initial time + transmit wave delay, matching USTB DAS.",
        "", "![Measured frames](frames.png)", "", "![Latency and memory](profile.png)", "",
        "[All measurements](metrics.json)", "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/raw/SWE_L7_type_I.uff"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/sequence"))
    args = parser.parse_args()
    run_sequence(args.dataset, args.output_dir)


if __name__ == "__main__":
    main()
