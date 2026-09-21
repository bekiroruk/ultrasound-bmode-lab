"""Loader for selected EPFL ultrafast in-vivo RF acquisitions."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from .real_data import UFFAcquisition

EPFL_CITATION = (
    "R. Viñals and J.-P. Thiran, Deep Learning-based Inpainting for Sparse "
    "Arrays in Ultrafast Ultrasound Imaging, IEEE Transactions on Computational Imaging, 2025."
)


def _yaml_number(text: str, field: str) -> float:
    match = re.search(rf"^\s*{re.escape(field)}:\s*([-+0-9.eE]+)", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing {field!r} in EPFL beamforming settings")
    return float(match.group(1))


def load_epfl_acquisition(
    path: str | Path,
    settings_dir: str | Path,
    lateral_pixels: int = 192,
    axial_pixels: int = 256,
) -> UFFAcquisition:
    """Load one EPFL RF tensor and construct its documented plane-wave geometry."""
    path = Path(path)
    settings_dir = Path(settings_dir)
    if not path.is_file():
        raise FileNotFoundError(
            f"EPFL acquisition not found: {path}. Run `python scripts/download_epfl.py`."
        )
    required = {
        "yaml": settings_dir / "beamforming_settings.yaml",
        "angles": settings_dir / "steering_angles.npy",
        "time": settings_dir / "time_axis.npy",
    }
    missing = [str(value) for value in required.values() if not value.is_file()]
    if missing:
        raise FileNotFoundError(f"EPFL settings are incomplete: {', '.join(missing)}")
    if lateral_pixels < 2 or axial_pixels < 2:
        raise ValueError("EPFL reconstruction grid must contain at least two pixels per axis")

    settings = required["yaml"].read_text(encoding="utf-8")
    sound_speed = _yaml_number(settings, "c0")
    sampling_frequency = _yaml_number(settings, "sampling_frequency")
    element_count = int(_yaml_number(settings, "n_elements"))
    pitch = _yaml_number(settings, "pitch")
    angles = np.asarray(np.load(required["angles"]), dtype=float)
    time_axis = np.asarray(np.load(required["time"]), dtype=float)

    with np.load(path) as archive:
        raw = np.asarray(archive["data"], dtype=np.float32)
        body_region = str(archive["body_region"].item())
        volunteer_id = str(archive["volunteer_id"].item())
    if raw.ndim != 4 or raw.shape[0] != 1:
        raise ValueError("expected EPFL data shape [1, transmit, element, sample]")
    channel = np.ascontiguousarray(raw[0])
    if channel.shape[:2] != (angles.size, element_count):
        raise ValueError("EPFL RF dimensions do not match the published settings")
    if channel.shape[-1] != time_axis.size:
        raise ValueError("EPFL sample count does not match the global time axis")
    measured_frequency = 1.0 / float(np.median(np.diff(time_axis)))
    if not np.isclose(measured_frequency, sampling_frequency, rtol=1e-6):
        raise ValueError("EPFL time axis is inconsistent with the sampling frequency")

    element_x = (np.arange(element_count) - (element_count - 1) / 2.0) * pitch
    x_axis = np.linspace(-20e-3, 20e-3, lateral_pixels)
    z_axis = np.linspace(5e-3, 65e-3, axial_pixels)
    return UFFAcquisition(
        channel_data=channel,
        sampling_frequency_hz=sampling_frequency,
        sound_speed_m_s=sound_speed,
        initial_time_s=float(time_axis[0]),
        element_x_m=element_x,
        transmit_angles_rad=angles,
        x_axis_m=x_axis,
        z_axis_m=z_axis,
        reference_iq=None,
        name=f"EPFL volunteer {volunteer_id} {body_region}",
        citation=EPFL_CITATION,
    )
