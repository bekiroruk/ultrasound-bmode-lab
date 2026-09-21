"""Register and quantify a carotid lumen ROI with bootstrap uncertainty."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle
from scipy.ndimage import shift

from .accelerated import numba_available, numba_plane_wave_delay_and_sum
from .processing import envelope_detect
from .real_data import load_picmus_uff, plane_wave_delay_and_sum, reference_bmode
from .roi import (
    bootstrap_cyst_metrics,
    estimate_translation,
    locate_carotid_lumen,
    wall_edge_sharpness,
)


def run_roi_analysis(dataset: Path, output_dir: Path, angle_count: int = 75) -> dict[str, object]:
    acquisition = load_picmus_uff(dataset)
    output_dir.mkdir(parents=True, exist_ok=True)
    reconstruction = (
        numba_plane_wave_delay_and_sum(acquisition, angle_count=angle_count)
        if numba_available()
        else plane_wave_delay_and_sum(acquisition, angle_count=angle_count)
    )
    reference_db = reference_bmode(acquisition)[::2, ::2]
    reference_envelope = np.abs(acquisition.reference_iq)[::2, ::2]
    candidate_db = reconstruction.bmode_db
    candidate_envelope = envelope_detect(reconstruction.rf)
    rows, columns = candidate_db.shape
    reference_db = reference_db[:rows, :columns]
    reference_envelope = reference_envelope[:rows, :columns]

    pixel_shift = estimate_translation(reference_db, candidate_db)
    registered_db = shift(candidate_db, pixel_shift, order=1, mode="nearest")
    registered_envelope = shift(candidate_envelope, pixel_shift, order=1, mode="nearest")
    roi = locate_carotid_lumen(reference_db, reconstruction.x_axis_m, reconstruction.z_axis_m)
    reference_metrics = bootstrap_cyst_metrics(
        reference_envelope, reconstruction.x_axis_m, reconstruction.z_axis_m, roi
    )
    candidate_metrics = bootstrap_cyst_metrics(
        registered_envelope, reconstruction.x_axis_m, reconstruction.z_axis_m, roi
    )
    report = {
        "angle_count": angle_count,
        "registration_shift_pixels": {"axial": pixel_shift[0], "lateral": pixel_shift[1]},
        "lumen_roi": {
            "center_x_mm": roi.center_x_m * 1e3,
            "center_z_mm": roi.center_z_m * 1e3,
            "radius_mm": roi.radius_m * 1e3,
        },
        "reference": {
            "metrics": reference_metrics,
            "wall_edge_sharpness_db_per_mm": wall_edge_sharpness(
                reference_db, reconstruction.x_axis_m, reconstruction.z_axis_m, roi
            ),
        },
        "our_registered_cpwc": {
            "metrics": candidate_metrics,
            "wall_edge_sharpness_db_per_mm": wall_edge_sharpness(
                registered_db, reconstruction.x_axis_m, reconstruction.z_axis_m, roi
            ),
        },
        "uncertainty_note": "Pixel bootstrap CI; spatial correlation is not modelled.",
    }
    (output_dir / "carotid_roi_metrics.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    panels = (
        ("UFF reference", reference_db),
        ("Our CPWC · before registration", candidate_db),
        ("Our CPWC · registered", registered_db),
    )
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 5.3))
    extent = [
        reconstruction.x_axis_m[0] * 1e3,
        reconstruction.x_axis_m[-1] * 1e3,
        reconstruction.z_axis_m[-1] * 1e3,
        reconstruction.z_axis_m[0] * 1e3,
    ]
    for axis, (title, image) in zip(axes, panels, strict=True):
        axis.imshow(image, cmap="gray", vmin=-60, vmax=0, extent=extent, aspect="equal")
        axis.add_patch(
            Circle(
                (roi.center_x_m * 1e3, roi.center_z_m * 1e3),
                roi.radius_m * 1e3,
                fill=False,
                color="#00e5ff",
                lw=1.8,
            )
        )
        axis.add_patch(
            Circle(
                (roi.center_x_m * 1e3, roi.center_z_m * 1e3),
                (roi.radius_m + 3e-3) * 1e3,
                fill=False,
                color="#ffcc00",
                lw=1.0,
            )
        )
        axis.set(title=title, xlabel="Lateral [mm]", ylabel="Depth [mm]")
    fig.suptitle("Registered carotid ROI · uncertainty-aware quality analysis", fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_dir / "carotid_roi_analysis.png", dpi=190, bbox_inches="tight")
    plt.close(fig)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/raw/PICMUS_carotid_cross.uff"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/roi"))
    parser.add_argument("--angles", type=int, default=75)
    args = parser.parse_args()
    report = run_roi_analysis(args.dataset, args.output_dir, args.angles)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
