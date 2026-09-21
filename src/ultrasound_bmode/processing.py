"""Post-beamforming B-mode processing stages."""

import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.signal import butter, hilbert, sosfiltfilt


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


def estimate_center_frequency(channel_data: np.ndarray, sampling_frequency_hz: float) -> float:
    """Estimate the RF carrier from a small deterministic channel subset."""
    data = np.asarray(channel_data)
    if data.ndim != 3:
        raise ValueError("channel_data must have shape [transmit, element, sample]")
    subset = data[:: max(1, data.shape[0] // 5), :: max(1, data.shape[1] // 16)]
    spectrum = np.mean(np.abs(np.fft.rfft(subset, axis=-1)) ** 2, axis=(0, 1))
    frequencies = np.fft.rfftfreq(data.shape[-1], 1.0 / sampling_frequency_hz)
    valid = (frequencies >= 0.5e6) & (frequencies <= 0.9 * sampling_frequency_hz / 2.0)
    if not np.any(valid):
        raise ValueError("sampling frequency is too low for RF center-frequency estimation")
    valid_indices = np.flatnonzero(valid)
    return float(frequencies[valid_indices[np.argmax(spectrum[valid])]])


def bandpass_rf(
    channel_data: np.ndarray,
    sampling_frequency_hz: float,
    center_frequency_hz: float | None = None,
    fractional_bandwidth: float = 0.9,
) -> tuple[np.ndarray, float]:
    """Apply a zero-phase Butterworth RF band-pass filter."""
    if not 0.0 < fractional_bandwidth < 2.0:
        raise ValueError("fractional_bandwidth must be between 0 and 2")
    center = center_frequency_hz or estimate_center_frequency(
        channel_data, sampling_frequency_hz
    )
    half_band = center * fractional_bandwidth / 2.0
    low = max(0.1e6, center - half_band)
    high = min(0.95 * sampling_frequency_hz / 2.0, center + half_band)
    if not low < high:
        raise ValueError("invalid RF pass band")
    sos = butter(4, [low, high], btype="bandpass", fs=sampling_frequency_hz, output="sos")
    filtered = sosfiltfilt(sos, channel_data, axis=-1)
    return np.asarray(filtered, dtype=np.float32), float(center)


def suppress_common_mode(channel_data: np.ndarray, strength: float = 0.35) -> np.ndarray:
    """Suppress element-common RF clutter while retaining aperture variation."""
    if not 0.0 <= strength <= 1.0:
        raise ValueError("strength must be between 0 and 1")
    common = np.median(channel_data, axis=-2, keepdims=True)
    return np.asarray(channel_data - strength * common, dtype=channel_data.dtype)


def automatic_tgc(
    envelope: np.ndarray,
    z_axis_m: np.ndarray,
    max_gain_db: float = 24.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate a smooth depth gain from the lateral 75th-percentile profile."""
    image = np.asarray(envelope, dtype=float)
    if image.ndim != 2 or image.shape[0] != z_axis_m.size:
        raise ValueError("envelope rows must match z_axis_m")
    profile = np.percentile(image, 75.0, axis=1)
    sigma = max(1.0, image.shape[0] / 80.0)
    profile = gaussian_filter1d(profile, sigma=sigma, mode="nearest")
    positive = profile[profile > np.finfo(float).eps]
    target = float(np.median(positive)) if positive.size else 1.0
    gain = target / np.maximum(profile, np.finfo(float).eps)
    gain = np.clip(gain, 10 ** (-max_gain_db / 20.0), 10 ** (max_gain_db / 20.0))
    return image * gain[:, None], gain


def adaptive_log_compress(
    envelope: np.ndarray,
    min_dynamic_range_db: float = 45.0,
    max_dynamic_range_db: float = 75.0,
) -> tuple[np.ndarray, float]:
    """Choose the display range from the measured envelope distribution."""
    normalized = np.asarray(envelope, dtype=float) / max(
        float(np.percentile(envelope, 99.9)), np.finfo(float).eps
    )
    raw_db = 20.0 * np.log10(np.maximum(normalized, np.finfo(float).eps))
    proposed = -float(np.percentile(raw_db, 5.0))
    dynamic_range = float(np.clip(proposed, min_dynamic_range_db, max_dynamic_range_db))
    return np.clip(raw_db, -dynamic_range, 0.0), dynamic_range


def anisotropic_diffusion(
    image: np.ndarray,
    iterations: int = 6,
    kappa: float = 8.0,
    step: float = 0.18,
) -> np.ndarray:
    """Apply Perona-Malik speckle smoothing while preserving strong edges."""
    if iterations < 0 or kappa <= 0 or not 0 < step <= 0.25:
        raise ValueError("invalid anisotropic-diffusion parameters")
    output = np.asarray(image, dtype=float).copy()
    for _ in range(iterations):
        north = np.zeros_like(output)
        south = np.zeros_like(output)
        west = np.zeros_like(output)
        east = np.zeros_like(output)
        north[1:] = output[:-1] - output[1:]
        south[:-1] = output[1:] - output[:-1]
        west[:, 1:] = output[:, :-1] - output[:, 1:]
        east[:, :-1] = output[:, 1:] - output[:, :-1]
        update = sum(
            gradient * np.exp(-((gradient / kappa) ** 2))
            for gradient in (north, south, west, east)
        )
        output += step * update
    return output
