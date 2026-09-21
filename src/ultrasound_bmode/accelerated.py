"""Optional compiled CPU backend for measured plane-wave DAS."""

from __future__ import annotations

import math

import numpy as np

from .processing import envelope_detect, log_compress
from .real_data import PlaneWaveResult, UFFAcquisition, select_transmit_indices

try:
    from numba import cuda, njit, prange
except ImportError:  # pragma: no cover - exercised only without acceleration extra
    cuda = None
    njit = None
    prange = range


if njit is not None:

    @njit(parallel=True, fastmath=True, cache=True)
    def _numba_das_kernel(
        channel_data,
        transmit_angles,
        angle_indices,
        element_x,
        x_axis,
        z_axis,
        sampling_frequency,
        sound_speed,
        initial_time,
        f_number,
    ):
        output = np.zeros((z_axis.size, x_axis.size), dtype=np.float64)
        for x_index in prange(x_axis.size):
            x_position = x_axis[x_index]
            for z_index in range(z_axis.size):
                depth = z_axis[z_index]
                half_aperture = max(depth / (2.0 * f_number), 1e-9)
                compounded = 0.0
                for selection_index in range(angle_indices.size):
                    angle_index = angle_indices[selection_index]
                    angle = transmit_angles[angle_index]
                    transmit_distance = x_position * np.sin(angle) + depth * np.cos(angle)
                    numerator = 0.0
                    normalizer = 0.0
                    for element_index in range(element_x.size):
                        offset = abs(element_x[element_index] - x_position)
                        normalized_offset = offset / half_aperture
                        if normalized_offset > 1.0:
                            continue
                        receive_distance = np.sqrt(
                            (x_position - element_x[element_index]) ** 2 + depth**2
                        )
                        sample_position = (
                            (transmit_distance + receive_distance) / sound_speed - initial_time
                        ) * sampling_frequency
                        lower = int(np.floor(sample_position))
                        if lower < 0 or lower + 1 >= channel_data.shape[2]:
                            continue
                        fraction = sample_position - lower
                        lower_value = channel_data[angle_index, element_index, lower]
                        upper_value = channel_data[angle_index, element_index, lower + 1]
                        delayed = lower_value * (1.0 - fraction) + upper_value * fraction
                        weight = 0.5 * (1.0 + np.cos(np.pi * normalized_offset))
                        numerator += delayed * weight
                        normalizer += weight
                    if normalizer > 0.0:
                        compounded += numerator / normalizer
                output[z_index, x_index] = compounded / angle_indices.size
        return output


if cuda is not None:

    @cuda.jit
    def _cuda_das_kernel(
        channel_data,
        transmit_angles,
        angle_indices,
        element_x,
        x_axis,
        z_axis,
        sampling_frequency,
        sound_speed,
        initial_time,
        f_number,
        output,
    ):
        pixel = cuda.grid(1)
        pixel_count = x_axis.size * z_axis.size
        if pixel >= pixel_count:
            return
        z_index = pixel // x_axis.size
        x_index = pixel - z_index * x_axis.size
        x_position = x_axis[x_index]
        depth = z_axis[z_index]
        half_aperture = max(depth / (2.0 * f_number), 1e-9)
        compounded = 0.0
        for selection_index in range(angle_indices.size):
            angle_index = angle_indices[selection_index]
            angle = transmit_angles[angle_index]
            transmit_distance = x_position * math.sin(angle) + depth * math.cos(angle)
            numerator = 0.0
            normalizer = 0.0
            for element_index in range(element_x.size):
                difference = x_position - element_x[element_index]
                normalized_offset = abs(difference) / half_aperture
                if normalized_offset > 1.0:
                    continue
                receive_distance = math.sqrt(difference * difference + depth * depth)
                sample_position = (
                    (transmit_distance + receive_distance) / sound_speed - initial_time
                ) * sampling_frequency
                lower = math.floor(sample_position)
                if lower < 0 or lower + 1 >= channel_data.shape[2]:
                    continue
                fraction = sample_position - lower
                delayed = (
                    channel_data[angle_index, element_index, lower] * (1.0 - fraction)
                    + channel_data[angle_index, element_index, lower + 1] * fraction
                )
                weight = 0.5 * (1.0 + math.cos(math.pi * normalized_offset))
                numerator += delayed * weight
                normalizer += weight
            if normalizer > 0.0:
                compounded += numerator / normalizer
        output[z_index, x_index] = compounded / angle_indices.size


def numba_available() -> bool:
    return njit is not None


def cuda_available() -> bool:
    if cuda is None:
        return False
    try:
        return bool(cuda.is_available())
    except RuntimeError:
        return False


def numba_plane_wave_delay_and_sum(
    acquisition: UFFAcquisition,
    angle_count: int = 11,
    lateral_stride: int = 2,
    axial_stride: int = 2,
    f_number: float = 1.5,
    dynamic_range_db: float = 60.0,
) -> PlaneWaveResult:
    """Run conventional CPWC with a parallel Numba CPU kernel."""
    if njit is None:
        raise ImportError("Numba backend requires `pip install -e .[accelerated]`")
    if lateral_stride <= 0 or axial_stride <= 0 or f_number <= 0:
        raise ValueError("strides and f_number must be positive")
    x_axis = np.ascontiguousarray(acquisition.x_axis_m[::lateral_stride])
    z_axis = np.ascontiguousarray(acquisition.z_axis_m[::axial_stride])
    angle_indices = np.ascontiguousarray(
        select_transmit_indices(acquisition.transmit_angles_rad, angle_count)
    )
    rf = _numba_das_kernel(
        np.ascontiguousarray(acquisition.channel_data),
        np.ascontiguousarray(acquisition.transmit_angles_rad),
        angle_indices,
        np.ascontiguousarray(acquisition.element_x_m),
        x_axis,
        z_axis,
        acquisition.sampling_frequency_hz,
        acquisition.sound_speed_m_s,
        acquisition.initial_time_s,
        f_number,
    )
    bmode = log_compress(envelope_detect(rf), dynamic_range_db)
    return PlaneWaveResult(rf, bmode, x_axis, z_axis, angle_indices)


def cuda_plane_wave_delay_and_sum(
    acquisition: UFFAcquisition,
    angle_count: int = 11,
    lateral_stride: int = 2,
    axial_stride: int = 2,
    f_number: float = 1.5,
    dynamic_range_db: float = 60.0,
) -> PlaneWaveResult:
    """Run the same conventional DAS equation on an available CUDA device."""
    if not cuda_available():
        raise RuntimeError("CUDA backend requested but no compatible device is available")
    x_axis = np.ascontiguousarray(acquisition.x_axis_m[::lateral_stride])
    z_axis = np.ascontiguousarray(acquisition.z_axis_m[::axial_stride])
    angle_indices = np.ascontiguousarray(
        select_transmit_indices(acquisition.transmit_angles_rad, angle_count)
    )
    output_device = cuda.device_array((z_axis.size, x_axis.size), dtype=np.float64)
    threads = 128
    blocks = math.ceil(output_device.size / threads)
    _cuda_das_kernel[blocks, threads](
        cuda.to_device(np.ascontiguousarray(acquisition.channel_data)),
        cuda.to_device(np.ascontiguousarray(acquisition.transmit_angles_rad)),
        cuda.to_device(angle_indices),
        cuda.to_device(np.ascontiguousarray(acquisition.element_x_m)),
        cuda.to_device(x_axis),
        cuda.to_device(z_axis),
        acquisition.sampling_frequency_hz,
        acquisition.sound_speed_m_s,
        acquisition.initial_time_s,
        f_number,
        output_device,
    )
    rf = output_device.copy_to_host()
    bmode = log_compress(envelope_detect(rf), dynamic_range_db)
    return PlaneWaveResult(rf, bmode, x_axis, z_axis, angle_indices)
