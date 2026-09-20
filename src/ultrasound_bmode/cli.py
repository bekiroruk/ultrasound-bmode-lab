"""Command-line demo and artifact export."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import numpy as np

from .config import ImagingConfig
from .pipeline import BModeResult, run_pipeline
from .simulation import make_resolution_phantom


def save_figure(result: BModeResult, path: Path) -> None:
    config = result.config
    extent = [
        config.line_positions_m[0] * 1e3,
        config.line_positions_m[-1] * 1e3,
        config.depth_axis_m[-1] * 1e3,
        config.depth_axis_m[0] * 1e3,
    ]
    fig, (ax_image, ax_profile) = plt.subplots(
        1, 2, figsize=(11.5, 6.2), gridspec_kw={"width_ratios": [1.0, 1.25]}
    )
    image = ax_image.imshow(
        result.bmode_db,
        cmap="gray",
        vmin=-config.dynamic_range_db,
        vmax=0,
        extent=extent,
        aspect="auto",
    )
    if result.metrics is not None:
        ax_image.add_patch(Circle((0, 30), 3.2, fill=False, edgecolor="#21d4fd", linewidth=1.4))
        ax_image.add_patch(Circle((0, 30), 8.0, fill=False, edgecolor="#f5a623", linewidth=1.0))
    ax_image.set(title="Reconstructed B-mode", xlabel="Lateral position [mm]", ylabel="Depth [mm]")
    fig.colorbar(image, ax=ax_image, label="Normalized amplitude [dB]", shrink=0.85)

    center_line = result.bmode_db[:, result.bmode_db.shape[1] // 2]
    ax_profile.plot(center_line, config.depth_axis_m * 1e3, color="#0066cc", linewidth=1.6)
    ax_profile.invert_yaxis()
    ax_profile.grid(alpha=0.25)
    ax_profile.set(
        title="Center-line depth profile",
        xlabel="Normalized amplitude [dB]",
        ylabel="Depth [mm]",
        xlim=(-config.dynamic_range_db, 0),
    )
    metric_text = (
        (
            f"Contrast: {result.metrics.contrast_db:.2f} dB\n"
            f"CNR: {result.metrics.cnr:.2f}\n"
            f"gCNR: {result.metrics.generalized_cnr:.2f}"
        )
        if result.metrics is not None
        else "Isolated reflectors\nfor PSF inspection"
    )
    ax_profile.text(
        0.04,
        0.96,
        metric_text,
        transform=ax_profile.transAxes,
        va="top",
        bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "#cccccc"},
    )
    fig.suptitle("Ultrasound B-mode Lab — Delay-and-Sum Reconstruction", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def save_clean_bmode(result: BModeResult, path: Path) -> None:
    """Export a presentation-ready B-mode frame without diagnostic overlays."""
    config = result.config
    extent = [
        config.line_positions_m[0] * 1e3,
        config.line_positions_m[-1] * 1e3,
        config.depth_axis_m[-1] * 1e3,
        config.depth_axis_m[0] * 1e3,
    ]
    fig, ax = plt.subplots(figsize=(6.4, 8.0), facecolor="#07090d")
    ax.set_facecolor("black")
    image = ax.imshow(
        result.bmode_db,
        cmap="gray",
        vmin=-50,
        vmax=0,
        extent=extent,
        aspect="auto",
        interpolation="bilinear",
    )
    ax.set(
        title="High-resolution B-mode reconstruction",
        xlabel="Lateral position [mm]",
        ylabel="Depth [mm]",
        ylim=(50, 5),
    )
    ax.title.set_color("white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("#7f8c9a")
    colorbar = fig.colorbar(image, ax=ax, pad=0.025, shrink=0.82)
    colorbar.set_label("Normalized amplitude [dB]", color="white")
    colorbar.ax.tick_params(colors="white")
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def save_pipeline_stages(result: BModeResult, path: Path) -> None:
    """Show the simulated object and three observable reconstruction stages."""
    config = result.config
    extent = [
        config.line_positions_m[0] * 1e3,
        config.line_positions_m[-1] * 1e3,
        config.depth_axis_m[-1] * 1e3,
        config.depth_axis_m[0] * 1e3,
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.5))
    phantom_ax, channel_ax, rf_ax, bmode_ax = axes.ravel()

    phantom_ax.scatter(
        result.phantom.x_m * 1e3,
        result.phantom.z_m * 1e3,
        c=np.abs(result.phantom.amplitude),
        cmap="magma",
        s=7,
        alpha=0.75,
        linewidths=0,
    )
    phantom_ax.set(
        title="1 · Digital phantom",
        xlabel="Lateral [mm]",
        ylabel="Depth [mm]",
        xlim=(extent[0], extent[1]),
        ylim=(50, 0),
    )

    center = config.line_count // 2
    time_depth_mm = (
        np.arange(config.rf_sample_count)
        / config.sampling_frequency_hz
        * config.sound_speed_m_s
        / 2
        * 1e3
    )
    channel_ax.imshow(
        result.channel_data[center].T,
        cmap="seismic",
        vmin=-0.25,
        vmax=0.25,
        extent=[0, config.element_count - 1, time_depth_mm[-1], time_depth_mm[0]],
        aspect="auto",
    )
    channel_ax.set(
        title="2 · Center-line RF channels",
        xlabel="Receive element",
        ylabel="Equivalent depth [mm]",
        ylim=(50, 0),
    )

    rf_limit = max(float(np.percentile(np.abs(result.beamformed_rf), 99.5)), 1e-9)
    rf_ax.imshow(
        result.beamformed_rf,
        cmap="seismic",
        vmin=-rf_limit,
        vmax=rf_limit,
        extent=extent,
        aspect="auto",
    )
    rf_ax.set(
        title="3 · Coherently beamformed RF",
        xlabel="Lateral [mm]",
        ylabel="Depth [mm]",
        ylim=(50, 5),
    )

    bmode_ax.imshow(
        result.bmode_db,
        cmap="gray",
        vmin=-50,
        vmax=0,
        extent=extent,
        aspect="auto",
        interpolation="bilinear",
    )
    bmode_ax.set(
        title="4 · Envelope + TGC + log compression",
        xlabel="Lateral [mm]",
        ylabel="Depth [mm]",
        ylim=(50, 5),
    )
    fig.suptitle("From simulated scatterers to a B-mode image", fontsize=16, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--lines", type=int, default=48)
    parser.add_argument("--elements", type=int, default=32)
    parser.add_argument("--phantom", choices=("cyst", "resolution"), default="cyst")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    config = ImagingConfig(line_count=args.lines, element_count=args.elements)
    phantom = make_resolution_phantom(config) if args.phantom == "resolution" else None
    result = run_pipeline(
        config=config,
        phantom=phantom,
        seed=args.seed,
        noise_std=0.0005 if args.phantom == "resolution" else 0.004,
        evaluate_cyst_roi=args.phantom == "cyst",
    )
    figure_path = args.output_dir / "bmode_demo.png"
    clean_path = args.output_dir / "bmode_clean.png"
    stages_path = args.output_dir / "pipeline_stages.png"
    metrics_path = args.output_dir / "metrics.json"
    save_figure(result, figure_path)
    save_clean_bmode(result, clean_path)
    save_pipeline_stages(result, stages_path)
    metric_values = result.metrics.to_dict() if result.metrics is not None else {}
    metrics_path.write_text(
        json.dumps(metric_values, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Saved {figure_path}")
    print(f"Saved {clean_path}")
    print(f"Saved {stages_path}")
    print(f"Saved {metrics_path}")
    print(json.dumps(metric_values, indent=2))


if __name__ == "__main__":
    main()
