"""Deterministic synthetic-aperture channel-data simulation.

This is an educational point-scatterer model, not a validated acoustic solver.
It models propagation delay, a band-limited pulse, transmit beam sensitivity,
geometric spreading, and frequency-dependent attenuation.
"""

from dataclasses import dataclass

import numpy as np

from .config import ImagingConfig


@dataclass(frozen=True)
class Phantom:
    x_m: np.ndarray
    z_m: np.ndarray
    amplitude: np.ndarray

    def __post_init__(self) -> None:
        if not (self.x_m.shape == self.z_m.shape == self.amplitude.shape):
            raise ValueError("Phantom arrays must have identical shapes")
        if np.any(self.z_m <= 0):
            raise ValueError("Scatterer depths must be positive")


def make_cyst_phantom(
    config: ImagingConfig,
    scatterer_count: int = 420,
    seed: int = 7,
) -> Phantom:
    """Create reproducible speckle, an anechoic cyst, and point targets."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(-config.image_width_m / 2, config.image_width_m / 2, scatterer_count)
    z = rng.uniform(5e-3, config.max_depth_m - 2e-3, scatterer_count)
    amplitude = rng.normal(0.0, 1.0, scatterer_count)

    cyst_center = np.array([0.0, 30e-3])
    in_cyst = (x - cyst_center[0]) ** 2 + (z - cyst_center[1]) ** 2 < (4e-3) ** 2
    amplitude[in_cyst] *= 0.03

    # Bright point targets make axial/lateral focusing visually measurable.
    point_x = np.array([-7e-3, 0.0, 7e-3, 0.0])
    point_z = np.array([15e-3, 20e-3, 25e-3, 42e-3])
    point_amplitude = np.full(point_x.shape, 7.0)
    return Phantom(
        x_m=np.concatenate([x, point_x]),
        z_m=np.concatenate([z, point_z]),
        amplitude=np.concatenate([amplitude, point_amplitude]),
    )


def _pulse(config: ImagingConfig) -> tuple[np.ndarray, np.ndarray]:
    half_duration = 2.5 / config.center_frequency_hz
    t = np.arange(
        -half_duration,
        half_duration + 1 / config.sampling_frequency_hz,
        1 / config.sampling_frequency_hz,
    )
    # A Gaussian-modulated sinusoid gives a controllable broadband RF pulse.
    sigma = 0.44 / (config.fractional_bandwidth * config.center_frequency_hz)
    wave = np.sin(2 * np.pi * config.center_frequency_hz * t) * np.exp(-0.5 * (t / sigma) ** 2)
    wave /= np.max(np.abs(wave))
    return t, wave


def simulate_channel_data(
    phantom: Phantom,
    config: ImagingConfig,
    noise_std: float = 0.004,
    seed: int = 19,
) -> np.ndarray:
    """Return RF data with shape ``[scan_line, receive_element, sample]``."""
    elements = config.element_positions_m
    lines = config.line_positions_m
    sample_count = config.rf_sample_count
    channel = np.zeros((config.line_count, config.element_count, sample_count), dtype=np.float32)
    pulse_t, pulse = _pulse(config)
    pulse_offsets = np.rint(pulse_t * config.sampling_frequency_hz).astype(int)
    element_indices = np.arange(config.element_count)

    for line_index, line_x in enumerate(lines):
        rf = channel[line_index]
        for sx, sz, reflectivity in zip(phantom.x_m, phantom.z_m, phantom.amplitude):
            beam_width = 0.7e-3 + sz / (2.0 * config.f_number)
            tx_sensitivity = np.exp(-0.5 * ((sx - line_x) / beam_width) ** 2)
            if tx_sensitivity < 1e-5:
                continue

            tx_distance = np.hypot(sx - line_x, sz)
            rx_distance = np.hypot(sx - elements, sz)
            total_distance = tx_distance + rx_distance
            center_samples = np.rint(
                total_distance / config.sound_speed_m_s * config.sampling_frequency_hz
            ).astype(int)

            path_cm = total_distance * 100.0
            frequency_mhz = config.center_frequency_hz / 1e6
            attenuation_db = config.tgc_db_cm_mhz * frequency_mhz * path_cm
            attenuation = 10.0 ** (-attenuation_db / 20.0)
            spreading = 1.0 / np.maximum(total_distance, 2e-3)
            weights = reflectivity * tx_sensitivity * attenuation * spreading

            for offset, pulse_value in zip(pulse_offsets, pulse):
                sample_indices = center_samples + offset
                valid = (sample_indices >= 0) & (sample_indices < sample_count)
                rf[element_indices[valid], sample_indices[valid]] += (
                    weights[valid] * pulse_value
                ).astype(np.float32)

    peak = float(np.max(np.abs(channel)))
    if peak > 0:
        channel /= peak
    rng = np.random.default_rng(seed)
    channel += rng.normal(0.0, noise_std, channel.shape).astype(np.float32)
    return channel

