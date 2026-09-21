"""UFF loading and plane-wave DAS for the public PICMUS in-vivo dataset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import hilbert

from .adaptive import (
    coherence_factor,
    delay_multiply_and_sum,
    mvdr_spatial_smoothing,
    normalized_das,
    phase_coherence_factor,
)
from .processing import envelope_detect, log_compress


@dataclass(frozen=True)
class UFFAcquisition:
    channel_data: np.ndarray
    sampling_frequency_hz: float
    sound_speed_m_s: float
    initial_time_s: float
    element_x_m: np.ndarray
    transmit_angles_rad: np.ndarray
    x_axis_m: np.ndarray
    z_axis_m: np.ndarray
    reference_iq: np.ndarray | None
    name: str
    citation: str


@dataclass(frozen=True)
class PlaneWaveResult:
    rf: np.ndarray
    bmode_db: np.ndarray
    x_axis_m: np.ndarray
    z_axis_m: np.ndarray
    angle_indices: np.ndarray


def _decode_uff_text(node) -> str:
    if hasattr(node, "keys"):
        keys = sorted(node.keys())
        if not keys:
            return ""
        node = node[keys[0]]
    values = np.asarray(node).ravel()
    return "".join(chr(int(value)) for value in values)


def load_uff_channel_data(path: str | Path) -> UFFAcquisition:
    """Load plane-wave channel data from UFF, with an optional image reference."""
    try:
        import h5py
    except ImportError as exc:  # pragma: no cover - exercised only in minimal installs
        raise ImportError("Reading UFF data requires h5py; install the project dependencies") from exc

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Dataset not found: {path}. Run `python scripts/download_picmus.py` first."
        )

    with h5py.File(path, "r") as uff:
        channel_group = uff["channel_data"]
        channel = np.asarray(channel_group["data"], dtype=np.float32)
        sampling_frequency = float(channel_group["sampling_frequency"][0, 0])
        sound_speed = float(channel_group["sound_speed"][0, 0])
        initial_time = float(channel_group["initial_time"][0, 0])
        element_x = np.asarray(channel_group["probe/geometry"])[0].astype(float)
        sequence = channel_group["sequence"]
        names = sorted(sequence.keys())
        angles = np.array(
            [float(sequence[name]["source/azimuth"][0, 0]) for name in names], dtype=float
        )

        if "scan" in uff:
            x_axis = np.asarray(uff["scan/x_axis"]).ravel().astype(float)
            z_axis = np.asarray(uff["scan/z_axis"]).ravel().astype(float)
        else:
            x_axis = np.linspace(float(element_x.min()), float(element_x.max()), 256)
            final_time = initial_time + (channel.shape[-1] - 1) / sampling_frequency
            maximum_depth = min(80e-3, 0.95 * final_time * sound_speed / 2.0)
            z_axis = np.linspace(2e-3, maximum_depth, 384)

        reference_iq = None
        if "beamformed_data" in uff:
            real = np.asarray(uff["beamformed_data/data/real"]).ravel()
            imag = np.asarray(uff["beamformed_data/data/imag"]).ravel()
            # UFF stores z as the fastest-changing coordinate in the flattened scan.
            reference_iq = (real + 1j * imag).reshape(x_axis.size, z_axis.size).T

        return UFFAcquisition(
            channel_data=channel,
            sampling_frequency_hz=sampling_frequency,
            sound_speed_m_s=sound_speed,
            initial_time_s=initial_time,
            element_x_m=element_x,
            transmit_angles_rad=angles,
            x_axis_m=x_axis,
            z_axis_m=z_axis,
            reference_iq=reference_iq,
            name=_decode_uff_text(channel_group["name"]),
            citation=_decode_uff_text(channel_group["reference"]),
        )


def load_picmus_uff(path: str | Path) -> UFFAcquisition:
    """Backward-compatible PICMUS loader built on the generic UFF reader."""
    acquisition = load_uff_channel_data(path)
    if acquisition.reference_iq is None:
        raise ValueError("PICMUS validation requires embedded beamformed reference data")
    return acquisition


def reference_bmode(
    acquisition: UFFAcquisition, dynamic_range_db: float = 60.0
) -> np.ndarray:
    if acquisition.reference_iq is None:
        raise ValueError("this acquisition does not contain an embedded beamformed reference")
    return log_compress(np.abs(acquisition.reference_iq), dynamic_range_db)


def _select_angles(total: int, count: int) -> np.ndarray:
    if count <= 0 or count > total:
        raise ValueError(f"angle_count must be between 1 and {total}")
    if count == 1:
        return np.array([total // 2], dtype=int)
    return np.unique(np.rint(np.linspace(0, total - 1, count)).astype(int))


def select_transmit_indices(angles_rad: np.ndarray, count: int) -> np.ndarray:
    """Select approximately uniform physical angles, independent of storage order."""
    angles = np.asarray(angles_rad, dtype=float)
    if angles.ndim != 1 or not np.isfinite(angles).all():
        raise ValueError("transmit angles must be a finite one-dimensional array")
    if count <= 0 or count > angles.size:
        raise ValueError(f"angle_count must be between 1 and {angles.size}")
    if count == angles.size:
        return np.arange(angles.size, dtype=int)
    if count == 1:
        return np.array([int(np.argmin(np.abs(angles)))], dtype=int)
    targets = np.linspace(float(angles.min()), float(angles.max()), count)
    selected = [int(np.argmin(np.abs(angles - target))) for target in targets]
    if len(set(selected)) != count:
        return _select_angles(angles.size, count)
    return np.asarray(selected, dtype=int)


def beamform_plane_wave(
    acquisition: UFFAcquisition,
    angle_index: int,
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
    f_number: float = 1.5,
    method: str = "das",
    mvdr_subarray_size: int = 16,
    diagonal_loading: float = 0.05,
) -> np.ndarray:
    """Focus one measured plane-wave transmission onto a Cartesian grid."""
    if not 0 <= angle_index < acquisition.transmit_angles_rad.size:
        raise IndexError("angle_index is outside the acquired transmit sequence")
    if f_number <= 0:
        raise ValueError("f_number must be positive")
    methods = {"das", "cf", "pcf", "dmas", "mvdr"}
    if method not in methods:
        raise ValueError(f"method must be one of {sorted(methods)}")

    elements = acquisition.element_x_m
    element_indices = np.arange(elements.size)[None, :]
    angle = acquisition.transmit_angles_rad[angle_index]
    real_angle_data = acquisition.channel_data[angle_index]
    angle_data = (
        hilbert(real_angle_data, axis=-1) if method in {"cf", "pcf", "mvdr"} else real_angle_data
    )
    output_dtype = complex if np.iscomplexobj(angle_data) else float
    focused_image = np.zeros((z_axis_m.size, x_axis_m.size), dtype=output_dtype)

    for x_index, x_position in enumerate(x_axis_m):
        transmit_distance = x_position * np.sin(angle) + z_axis_m * np.cos(angle)
        receive_distance = np.hypot(x_position - elements[None, :], z_axis_m[:, None])
        sample_positions = (
            (transmit_distance[:, None] + receive_distance)
            / acquisition.sound_speed_m_s
            - acquisition.initial_time_s
        ) * acquisition.sampling_frequency_hz
        lower = np.floor(sample_positions).astype(np.int64)
        fraction = sample_positions - lower
        valid = (lower >= 0) & (lower + 1 < angle_data.shape[-1])
        safe_lower = np.clip(lower, 0, angle_data.shape[-1] - 2)
        lower_values = angle_data[element_indices, safe_lower]
        upper_values = angle_data[element_indices, safe_lower + 1]
        delayed = lower_values * (1.0 - fraction) + upper_values * fraction

        half_aperture = np.maximum(z_axis_m[:, None] / (2.0 * f_number), 1e-9)
        normalized_offset = np.abs(elements[None, :] - x_position) / half_aperture
        weights = np.where(
            normalized_offset <= 1.0,
            0.5 * (1.0 + np.cos(np.pi * normalized_offset)),
            0.0,
        )
        weights *= valid
        das = normalized_das(delayed, weights)
        if method == "das":
            focused = das
        elif method == "cf":
            focused = das * coherence_factor(delayed, weights)
        elif method == "pcf":
            focused = das * phase_coherence_factor(delayed, weights)
        elif method == "dmas":
            focused = delay_multiply_and_sum(delayed, weights)
        else:
            focused = np.array(
                [
                    mvdr_spatial_smoothing(
                        row,
                        row_weights,
                        subarray_size=mvdr_subarray_size,
                        diagonal_loading=diagonal_loading,
                    )
                    for row, row_weights in zip(delayed, weights, strict=True)
                ]
            )
        focused_image[:, x_index] = focused

    return focused_image


def plane_wave_delay_and_sum(
    acquisition: UFFAcquisition,
    angle_count: int = 11,
    lateral_stride: int = 2,
    axial_stride: int = 2,
    f_number: float = 1.5,
    dynamic_range_db: float = 60.0,
    method: str = "das",
    mvdr_subarray_size: int = 16,
    diagonal_loading: float = 0.05,
) -> PlaneWaveResult:
    """Reconstruct real RF data using coherent plane-wave compounding.

    The UFF channel array is stored as ``[transmit, element, sample]``. Linear
    interpolation implements fractional delays; a cosine receive aperture is
    varied with depth according to the requested F-number.
    """
    if lateral_stride <= 0 or axial_stride <= 0 or f_number <= 0:
        raise ValueError("strides and f_number must be positive")

    x_axis = acquisition.x_axis_m[::lateral_stride]
    z_axis = acquisition.z_axis_m[::axial_stride]
    angle_indices = select_transmit_indices(acquisition.transmit_angles_rad, angle_count)
    output_dtype = complex if method in {"cf", "pcf", "mvdr"} else float
    compounded = np.zeros((z_axis.size, x_axis.size), dtype=output_dtype)

    for angle_index in angle_indices:
        compounded += beamform_plane_wave(
            acquisition,
            int(angle_index),
            x_axis,
            z_axis,
            f_number,
            method,
            mvdr_subarray_size,
            diagonal_loading,
        )

    compounded /= angle_indices.size
    envelope = np.abs(compounded) if np.iscomplexobj(compounded) else envelope_detect(compounded)
    bmode = log_compress(envelope, dynamic_range_db)
    return PlaneWaveResult(compounded, bmode, x_axis, z_axis, angle_indices)
