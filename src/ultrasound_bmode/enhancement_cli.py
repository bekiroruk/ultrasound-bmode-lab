"""Evaluate an RF-to-display image-enhancement chain on measured carotid data."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .metrics import evaluate_similarity
from .processing import (
    adaptive_log_compress,
    anisotropic_diffusion,
    automatic_tgc,
    bandpass_rf,
    envelope_detect,
    log_compress,
    suppress_common_mode,
)
from .real_data import load_picmus_uff, plane_wave_delay_and_sum, reference_bmode


def run_enhancement(
    dataset: Path,
    output_dir: Path,
    angle_count: int = 11,
) -> dict[str, object]:
    acquisition = load_picmus_uff(dataset)
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline = plane_wave_delay_and_sum(acquisition, angle_count=angle_count)

    start = time.perf_counter()
    clutter_suppressed = suppress_common_mode(acquisition.channel_data)
    filtered, center_frequency = bandpass_rf(
        clutter_suppressed, acquisition.sampling_frequency_hz
    )
    enhanced_acquisition = replace(acquisition, channel_data=filtered)
    filtered_result = plane_wave_delay_and_sum(enhanced_acquisition, angle_count=angle_count)
    envelope = envelope_detect(filtered_result.rf)
    tgc_envelope, gain = automatic_tgc(envelope, filtered_result.z_axis_m)
    adaptive_db, dynamic_range = adaptive_log_compress(tgc_envelope)
    despeckled_db = anisotropic_diffusion(adaptive_db)
    runtime = time.perf_counter() - start

    reference = reference_bmode(acquisition)[::2, ::2]
    rows, columns = baseline.bmode_db.shape
    reference = reference[:rows, :columns]
    stages = {
        "baseline": baseline.bmode_db,
        "rf_preprocessed": log_compress(envelope),
        "auto_tgc_adaptive_dr": adaptive_db,
        "edge_preserving_despeckle": despeckled_db,
    }
    metrics = {}
    for name, image in stages.items():
        result = evaluate_similarity(reference, image)
        metrics[name] = result.to_dict()

    report = {
        "angle_count": angle_count,
        "estimated_center_frequency_hz": center_frequency,
        "adaptive_dynamic_range_db": dynamic_range,
        "tgc_gain_min_db": float(20.0 * np.log10(gain.min())),
        "tgc_gain_max_db": float(20.0 * np.log10(gain.max())),
        "enhancement_runtime_seconds": runtime,
        "similarity_to_uff_reference": metrics,
    }
    (output_dir / "enhancement_metrics.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    panels = [
        ("Baseline CPWC", stages["baseline"]),
        ("RF band-pass + clutter suppression", stages["rf_preprocessed"]),
        (f"Auto TGC + adaptive {dynamic_range:.0f} dB", adaptive_db),
        ("Edge-preserving despeckle", despeckled_db),
        ("UFF reference", reference),
    ]
    fig, axes = plt.subplots(1, 5, figsize=(17.5, 5.7))
    extent = [
        acquisition.x_axis_m[0] * 1e3,
        acquisition.x_axis_m[-1] * 1e3,
        acquisition.z_axis_m[-1] * 1e3,
        acquisition.z_axis_m[0] * 1e3,
    ]
    for axis, (title, image) in zip(axes, panels, strict=True):
        axis.imshow(
            image,
            cmap="gray",
            vmin=-dynamic_range,
            vmax=0,
            extent=extent,
            aspect="equal",
            interpolation="bilinear",
        )
        axis.set(title=title, xlabel="Lateral [mm]", ylabel="Depth [mm]")
    fig.suptitle("Measured carotid RF · image-enhancement ablation", fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_dir / "enhancement_ablation.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/raw/PICMUS_carotid_cross.uff"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/enhancement"))
    parser.add_argument("--angles", type=int, default=11)
    args = parser.parse_args()
    report = run_enhancement(args.dataset, args.output_dir, args.angles)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
