"""Compare legacy and channel-analytic CPWC against embedded UFF references."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .accelerated import numba_plane_wave_delay_and_sum
from .metrics import evaluate_similarity
from .real_data import load_picmus_uff, plane_wave_delay_and_sum, reference_bmode


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _save_comparison(legacy, analytic, reference, title: str, output: Path):
    fig, axes = plt.subplots(1, 3, figsize=(12, 5.5), layout="constrained")
    extent = [
        legacy.x_axis_m[0] * 1e3, legacy.x_axis_m[-1] * 1e3,
        legacy.z_axis_m[-1] * 1e3, legacy.z_axis_m[0] * 1e3,
    ]
    panels = (
        (legacy.bmode_db, "Before: output-grid Hilbert"),
        (analytic.bmode_db, "After: channel-analytic CPWC"),
        (reference, "Embedded UFF reference"),
    )
    for axis, (values, label) in zip(axes, panels, strict=True):
        display = axis.imshow(
            values, cmap="gray", vmin=-60, vmax=0, extent=extent,
            aspect="equal", interpolation="nearest",
        )
        axis.set(title=label, xlabel="Lateral [mm]", ylabel="Depth [mm]")
    fig.colorbar(display, ax=axes, shrink=0.65, label="Normalized amplitude [dB]")
    fig.suptitle(title + "\nSame RF, grid, angles and aperture; no denoising or sharpening")
    fig.savefig(output, dpi=180)
    plt.close(fig)


def run_quality_comparison(
    paths: list[Path], output_dir: Path, angle_counts: list[int],
    stride: int = 2, f_number: float = 1.5, backend: str = "numba",
) -> dict:
    if backend not in {"numpy", "numba"}:
        raise ValueError("backend must be numpy or numba")
    if stride <= 0 or not np.isfinite(f_number) or f_number <= 0:
        raise ValueError("stride and f_number must be positive and finite")
    if not paths or not angle_counts:
        raise ValueError("at least one dataset and angle count are required")
    output_dir.mkdir(parents=True, exist_ok=True)
    reconstruct = numba_plane_wave_delay_and_sum if backend == "numba" else plane_wave_delay_and_sum
    report = {
        "experiment": "Channel-analytic CPWC vs legacy output-grid Hilbert",
        "backend": backend,
        "python_version": platform.python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "matplotlib")},
        "stride_axial_and_lateral": stride,
        "f_number": f_number,
        "dynamic_range_db": 60,
        "reference_policy": "Embedded UFF reference only; no self-reconstruction references",
        "normalization": "Each image peak-normalized; reference normalized before grid subsampling",
        "nonfinite_metric_policy": "Undefined correlation or infinite PSNR is stored as null",
        "limitations": (
            "Reference similarity is not ground-truth or clinical accuracy. Analytic RF is not "
            "baseband IQ. No denoising, sharpening, registration, or contrast optimization. "
            "CUDA and native C++ paths remain legacy real-RF only."
        ),
        "results": [],
    }
    lines = [
        "# Channel-analytic reconstruction comparison", "",
        "Measured RF only. Each before/after pair uses identical angles, aperture and grid.",
        "Reference: independently stored UFF beamformed image (not anatomical ground truth).", "",
        "| Acquisition | Angles | SSIM before → after | RMSE dB before → after | Figure |",
        "|---|---:|---:|---:|---|",
    ]
    for path in paths:
        acquisition = load_picmus_uff(path)
        if min(acquisition.z_axis_m[::stride].size, acquisition.x_axis_m[::stride].size) < 2:
            raise ValueError("comparison grid requires at least two pixels in each dimension")
        dataset_hash = _sha256(path)
        reference = reference_bmode(acquisition)[::stride, ::stride]
        for count in angle_counts:
            kwargs = {
                "angle_count": count, "axial_stride": stride,
                "lateral_stride": stride, "f_number": f_number,
            }
            legacy = reconstruct(acquisition, **kwargs)
            analytic = reconstruct(acquisition, analytic=True, **kwargs)
            before = evaluate_similarity(reference, legacy.bmode_db).to_dict()
            after = evaluate_similarity(reference, analytic.bmode_db).to_dict()
            for metrics in (before, after):
                # Perfect matches have infinite PSNR; null keeps strict JSON valid.
                for key, value in metrics.items():
                    if not np.isfinite(value):
                        metrics[key] = None
            filename = f"{path.stem}_{count}_angles.png"
            _save_comparison(
                legacy, analytic, reference, f"{path.stem} · {count} angles", output_dir / filename
            )
            dz = float(np.median(np.diff(analytic.z_axis_m)))
            report["results"].append({
                "dataset": path.name,
                "sha256": dataset_hash,
                "acquisition_name": acquisition.name,
                "citation": acquisition.citation,
                "sampling_frequency_hz": acquisition.sampling_frequency_hz,
                "sound_speed_m_s": acquisition.sound_speed_m_s,
                "initial_time_s": acquisition.initial_time_s,
                "channel_shape": list(acquisition.channel_data.shape),
                "angle_count": count,
                "angle_indices": analytic.angle_indices.tolist(),
                "output_shape": list(analytic.bmode_db.shape),
                "axial_step_mm": dz * 1e3,
                "on_axis_output_rf_nyquist_hz": acquisition.sound_speed_m_s / (4 * dz),
                "legacy": before,
                "analytic": after,
                "figure": filename,
            })
            lines.append(
                f"| {path.stem} | {count} | {before['ssim']:.3f} → {after['ssim']:.3f} "
                f"| {before['rmse_db']:.2f} → {after['rmse_db']:.2f} | [Compare]({filename}) |"
            )
            print(f"{path.stem}, {count} angles: SSIM {before['ssim']:.4f} -> {after['ssim']:.4f}",
                  flush=True)
    (output_dir / "quality_metrics.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    lines += [
        "", f"Settings: {backend}; axial/lateral stride {stride}; F-number {f_number}; 60 dB.",
        "", report["normalization"] + ".", "", report["limitations"], "",
        "Exact selected indices, file SHA-256 values and metrics: [JSON](quality_metrics.json).", "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", type=Path, nargs="+", default=[
        Path("data/raw/PICMUS_carotid_cross.uff"),
        Path("data/raw/PICMUS_carotid_long.uff"),
        Path("data/raw/PICMUS_experiment_contrast_speckle.uff"),
        Path("data/raw/PICMUS_experiment_resolution_distortion.uff"),
    ])
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/analytic_quality"))
    parser.add_argument("--angles", type=int, nargs="+", default=[11, 75])
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--f-number", type=float, default=1.5)
    parser.add_argument("--backend", choices=["numpy", "numba"], default="numba")
    args = parser.parse_args()
    run_quality_comparison(
        args.datasets, args.output_dir, args.angles, args.stride, args.f_number, args.backend
    )


if __name__ == "__main__":
    main()
