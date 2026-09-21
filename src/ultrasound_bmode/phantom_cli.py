"""Reconstruct and quantify real CIRS phantom measurements from PICMUS."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle

from .phantom import NOMINAL_POINT_TARGETS_M, measure_contrast_phantom, measure_resolution_phantom
from .processing import envelope_detect
from .real_data import load_picmus_uff, plane_wave_delay_and_sum, reference_bmode


def _extent(acquisition) -> list[float]:
    return [
        acquisition.x_axis_m[0] * 1e3,
        acquisition.x_axis_m[-1] * 1e3,
        acquisition.z_axis_m[-1] * 1e3,
        acquisition.z_axis_m[0] * 1e3,
    ]


def _draw_measurement_figure(contrast, resolution, contrast_result, resolution_result, output):
    panels = (
        (contrast, reference_bmode(contrast), "Contrast phantom · UFF reference", "contrast"),
        (contrast, contrast_result.bmode_db, "Contrast phantom · our CPWC", "contrast"),
        (resolution, reference_bmode(resolution), "Resolution phantom · UFF reference", "resolution"),
        (resolution, resolution_result.bmode_db, "Resolution phantom · our CPWC", "resolution"),
    )
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 12.0))
    for axis, (acquisition, image, title, kind) in zip(axes.ravel(), panels, strict=True):
        axis.imshow(
            image,
            cmap="gray",
            vmin=-60,
            vmax=0,
            extent=_extent(acquisition),
            aspect="equal",
            interpolation="bilinear",
        )
        axis.set(title=title, xlabel="Lateral [mm]", ylabel="Depth [mm]")
        if kind == "contrast":
            for depth_mm in (15.0, 43.0):
                axis.add_patch(Circle((0, depth_mm), 1.5, fill=False, color="#00e5ff", lw=1.6))
                axis.add_patch(Circle((0, depth_mm), 4.5, fill=False, color="#ffcc00", lw=1.0))
            axis.add_patch(Circle((10, 28), 3, fill=False, color="#ff5ea8", lw=1.4))
        else:
            x = [point[0] * 1e3 for point in NOMINAL_POINT_TARGETS_M]
            z = [point[1] * 1e3 for point in NOMINAL_POINT_TARGETS_M]
            axis.scatter(x, z, s=34, facecolors="none", edgecolors="#00e5ff", linewidths=1.3)
    fig.suptitle("Physical CIRS phantom validation · measured RF data", fontweight="bold")
    fig.tight_layout()
    fig.savefig(output, dpi=190, bbox_inches="tight")
    plt.close(fig)


def run_phantom_validation(
    contrast_path: Path,
    resolution_path: Path,
    output_dir: Path,
    angle_count: int = 11,
) -> dict[str, object]:
    contrast = load_picmus_uff(contrast_path)
    resolution = load_picmus_uff(resolution_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    contrast_result = plane_wave_delay_and_sum(contrast, angle_count=angle_count, f_number=1.7)
    contrast_runtime = time.perf_counter() - start
    start = time.perf_counter()
    resolution_result = plane_wave_delay_and_sum(resolution, angle_count=angle_count, f_number=1.7)
    resolution_runtime = time.perf_counter() - start

    contrast_reference = measure_contrast_phantom(
        np.abs(contrast.reference_iq), contrast.x_axis_m, contrast.z_axis_m
    )
    contrast_ours = measure_contrast_phantom(
        envelope_detect(contrast_result.rf), contrast_result.x_axis_m, contrast_result.z_axis_m
    )
    resolution_reference = measure_resolution_phantom(
        np.abs(resolution.reference_iq), resolution.x_axis_m, resolution.z_axis_m
    )
    resolution_ours = measure_resolution_phantom(
        envelope_detect(resolution_result.rf), resolution_result.x_axis_m, resolution_result.z_axis_m
    )
    metrics = {
        "dataset": "PICMUS experimental CIRS Multi-Purpose Ultrasound Phantom 040GSE",
        "source_doi": "10.5281/zenodo.20261898",
        "angle_count": angle_count,
        "contrast_runtime_seconds": contrast_runtime,
        "resolution_runtime_seconds": resolution_runtime,
        "reference": {
            "contrast": contrast_reference,
            "resolution": resolution_reference,
        },
        "our_cpwc": {
            "contrast": contrast_ours,
            "resolution": resolution_ours,
        },
    }
    (output_dir / "phantom_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    _draw_measurement_figure(
        contrast,
        resolution,
        contrast_result,
        resolution_result,
        output_dir / "physical_phantom_validation.png",
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contrast-dataset",
        type=Path,
        default=Path("data/raw/PICMUS_experiment_contrast_speckle.uff"),
    )
    parser.add_argument(
        "--resolution-dataset",
        type=Path,
        default=Path("data/raw/PICMUS_experiment_resolution_distortion.uff"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/phantom"))
    parser.add_argument("--angles", type=int, default=11)
    args = parser.parse_args()
    metrics = run_phantom_validation(
        args.contrast_dataset,
        args.resolution_dataset,
        args.output_dir,
        args.angles,
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
