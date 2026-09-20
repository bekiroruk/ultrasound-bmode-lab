"""Dynamic-receive delay-and-sum beamforming."""

import numpy as np

from .config import ImagingConfig


def _aperture_weights(element_offsets: np.ndarray, depth_m: float, f_number: float) -> np.ndarray:
    half_aperture = max(depth_m / (2 * f_number), np.finfo(float).eps)
    active = np.abs(element_offsets) <= half_aperture
    count = int(np.count_nonzero(active))
    weights = np.zeros_like(element_offsets, dtype=float)
    if count == 1:
        weights[active] = 1.0
    elif count > 1:
        weights[active] = np.hanning(count)
    return weights


def delay_and_sum(channel_data: np.ndarray, config: ImagingConfig) -> np.ndarray:
    """Beamform RF channel data on the configured Cartesian scan grid.

    Linear interpolation implements fractional sample delays. A depth-dependent
    F-number aperture and Hanning apodization reduce sidelobes.
    """
    expected = (config.line_count, config.element_count, config.rf_sample_count)
    if channel_data.shape != expected:
        raise ValueError(f"Expected channel data shape {expected}, got {channel_data.shape}")

    depths = config.depth_axis_m
    lines = config.line_positions_m
    elements = config.element_positions_m
    beamformed = np.zeros((depths.size, lines.size), dtype=np.float32)

    for line_index, line_x in enumerate(lines):
        element_offsets = elements - line_x
        for depth_index, depth in enumerate(depths):
            tx_distance = depth
            rx_distance = np.hypot(element_offsets, depth)
            sample_positions = (
                (tx_distance + rx_distance)
                / config.sound_speed_m_s
                * config.sampling_frequency_hz
            )
            lower = np.floor(sample_positions).astype(int)
            fraction = sample_positions - lower
            valid = (lower >= 0) & (lower + 1 < channel_data.shape[-1])
            if not np.any(valid):
                continue

            element_idx = np.arange(config.element_count)[valid]
            lo = channel_data[line_index, element_idx, lower[valid]]
            hi = channel_data[line_index, element_idx, lower[valid] + 1]
            delayed = lo * (1.0 - fraction[valid]) + hi * fraction[valid]
            weights = _aperture_weights(element_offsets, depth, config.f_number)[valid]
            normalizer = np.sum(np.abs(weights))
            if normalizer > 0:
                beamformed[depth_index, line_index] = np.sum(delayed * weights) / normalizer

    return beamformed

