"""Post-beamforming B-mode processing stages."""

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.signal import hilbert


def envelope_detect(rf_image: np.ndarray, axis: int = 0) -> np.ndarray:
    """Estimate the RF magnitude envelope using the analytic signal."""
    if rf_image.ndim != 2:
        raise ValueError("rf_image must be two-dimensional")
    return np.abs(hilbert(rf_image, axis=axis))


def time_gain_compensation(
    envelope: np.ndarray,
    depths_m: np.ndarray,
    center_frequency_hz: float,
    attenuation_db_cm_mhz: float,
) -> np.ndarray:
    """Apply a depth-dependent gain matching a two-way attenuation model."""
    depth_cm = np.asarray(depths_m) * 100.0
    frequency_mhz = center_frequency_hz / 1e6
    gain_db = 2.0 * attenuation_db_cm_mhz * frequency_mhz * depth_cm
    gain = 10.0 ** (gain_db / 20.0)
    return envelope * gain[:, None]


def log_compress(envelope: np.ndarray, dynamic_range_db: float = 60.0) -> np.ndarray:
    """Normalize and map an envelope image to ``[-dynamic_range_db, 0]`` dB."""
    if dynamic_range_db <= 0:
        raise ValueError("dynamic_range_db must be positive")
    peak = float(np.max(envelope))
    if peak <= 0:
        return np.full_like(envelope, -dynamic_range_db, dtype=float)
    db = 20.0 * np.log10(np.maximum(envelope / peak, 1e-12))
    return np.clip(db, -dynamic_range_db, 0.0)


def scan_convert_linear(db_image: np.ndarray, lateral_sigma_px: float = 0.45) -> np.ndarray:
    """Place linear-array scan lines on a Cartesian grid with mild interpolation.

    Linear arrays are natively Cartesian, so scan conversion is identity in
    geometry. Sub-pixel Gaussian interpolation suppresses line-to-line staircasing.
    """
    return gaussian_filter(db_image, sigma=(0.0, lateral_sigma_px), mode="nearest")

