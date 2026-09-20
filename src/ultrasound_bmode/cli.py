"""Command-line demo and artifact export."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from .config import ImagingConfig
from .pipeline import BModeResult, run_pipeline


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
        f"Contrast: {result.metrics.contrast_db:.2f} dB\n"
        f"CNR: {result.metrics.cnr:.2f}\n"
        f"gCNR: {result.metrics.generalized_cnr:.2f}"
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--lines", type=int, default=48)
    parser.add_argument("--elements", type=int, default=32)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    config = ImagingConfig(line_count=args.lines, element_count=args.elements)
    result = run_pipeline(config=config, seed=args.seed)
    figure_path = args.output_dir / "bmode_demo.png"
    metrics_path = args.output_dir / "metrics.json"
    save_figure(result, figure_path)
    metrics_path.write_text(
        json.dumps(result.metrics.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Saved {figure_path}")
    print(f"Saved {metrics_path}")
    print(json.dumps(result.metrics.to_dict(), indent=2))


if __name__ == "__main__":
    main()

