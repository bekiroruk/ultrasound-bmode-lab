"""Reconstruct and visualize public PICMUS in-vivo carotid channel data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .metrics import evaluate_similarity
from .real_data import (
    UFFAcquisition,
    load_picmus_uff,
    plane_wave_delay_and_sum,
    reference_bmode,
)


def _extent(x_axis_m: np.ndarray, z_axis_m: np.ndarray) -> list[float]:
    return [x_axis_m[0] * 1e3, x_axis_m[-1] * 1e3, z_axis_m[-1] * 1e3, z_axis_m[0] * 1e3]


def save_clean_reference(acquisition: UFFAcquisition, output: Path) -> None:
    image = reference_bmode(acquisition)
    fig, ax = plt.subplots(figsize=(7.2, 8.2), facecolor="#07090d")
    ax.set_facecolor("black")
    display = ax.imshow(
        image,
        cmap="gray",
        vmin=-60,
        vmax=0,
        extent=_extent(acquisition.x_axis_m, acquisition.z_axis_m),
        aspect="equal",
        interpolation="bilinear",
    )
    ax.set(
        title="PICMUS in-vivo carotid · 75-angle CPWC",
        xlabel="Lateral position [mm]",
        ylabel="Depth [mm]",
    )
    ax.title.set_color("white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("#7f8c9a")
    colorbar = fig.colorbar(display, ax=ax, pad=0.025, shrink=0.82)
    colorbar.set_label("Normalized amplitude [dB]", color="white")
    colorbar.ax.tick_params(colors="white")
    fig.tight_layout()
    fig.savefig(output, dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def save_comparison(
    acquisition: UFFAcquisition,
    single,
    compounded,
    output: Path,
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    channel_ax, single_ax, compound_ax, reference_ax = axes.ravel()
    center_data = acquisition.channel_data[acquisition.channel_data.shape[0] // 2]
    sample_depth = (
        np.arange(center_data.shape[-1])
        / acquisition.sampling_frequency_hz
        * acquisition.sound_speed_m_s
        / 2
        * 1e3
    )
    channel_limit = max(float(np.percentile(np.abs(center_data), 99.5)), 1e-9)
    channel_ax.imshow(
        center_data.T,
        cmap="seismic",
        vmin=-channel_limit,
        vmax=channel_limit,
        extent=[0, center_data.shape[0] - 1, sample_depth[-1], sample_depth[0]],
        aspect="auto",
    )
    channel_ax.set(
        title="Measured RF · 0° plane wave",
        xlabel="Receive element",
        ylabel="Equivalent depth [mm]",
    )

    panels = [
        (single_ax, single.bmode_db, single.x_axis_m, single.z_axis_m, "Our DAS · 1 angle"),
        (
            compound_ax,
            compounded.bmode_db,
            compounded.x_axis_m,
            compounded.z_axis_m,
            f"Our CPWC · {compounded.angle_indices.size} angles",
        ),
        (
            reference_ax,
            reference_bmode(acquisition),
            acquisition.x_axis_m,
            acquisition.z_axis_m,
            "UFF reference · 75 angles",
        ),
    ]
    for axis, image, x_axis, z_axis, title in panels:
        axis.imshow(
            image,
            cmap="gray",
            vmin=-60,
            vmax=0,
            extent=_extent(x_axis, z_axis),
            aspect="equal",
            interpolation="bilinear",
        )
        axis.set(title=title, xlabel="Lateral [mm]", ylabel="Depth [mm]")

    fig.suptitle(
        "Real device data: coherent plane-wave compounding",
        fontsize=16,
        fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def similarity_metrics(acquisition: UFFAcquisition, result) -> dict[str, float]:
    reference = reference_bmode(acquisition)[::2, ::2]
    candidate = result.bmode_db
    rows = min(reference.shape[0], candidate.shape[0])
    columns = min(reference.shape[1], candidate.shape[1])
    reference = reference[:rows, :columns]
    candidate = candidate[:rows, :columns]
    metrics = evaluate_similarity(reference, candidate)
    return {
        "reference_correlation": metrics.correlation,
        "rmse_db": metrics.rmse_db,
        "ssim": metrics.ssim,
        "psnr_db": metrics.psnr_db,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/raw/PICMUS_carotid_cross.uff"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/real_data"))
    parser.add_argument("--angles", type=int, default=11)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    acquisition = load_picmus_uff(args.dataset)
    single = plane_wave_delay_and_sum(acquisition, angle_count=1)
    compounded = plane_wave_delay_and_sum(acquisition, angle_count=args.angles)
    clean_path = args.output_dir / "picmus_carotid_75_angle.png"
    comparison_path = args.output_dir / "picmus_reconstruction_comparison.png"
    metrics_path = args.output_dir / "real_data_metrics.json"
    save_clean_reference(acquisition, clean_path)
    save_comparison(acquisition, single, compounded, comparison_path)
    metrics = similarity_metrics(acquisition, compounded)
    metadata = {
        "dataset_name": acquisition.name,
        "source": "USTB/PICMUS via Zenodo",
        "doi": "10.5281/zenodo.20261898",
        "license": "CC BY 4.0",
        "citation": acquisition.citation,
        "sampling_frequency_hz": acquisition.sampling_frequency_hz,
        "sound_speed_m_s": acquisition.sound_speed_m_s,
        "receive_elements": int(acquisition.element_x_m.size),
        "available_plane_waves": int(acquisition.transmit_angles_rad.size),
        "implemented_compounding_angles": int(compounded.angle_indices.size),
        **metrics,
    }
    metrics_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    print(f"Saved {clean_path}")
    print(f"Saved {comparison_path}")


if __name__ == "__main__":
    main()
