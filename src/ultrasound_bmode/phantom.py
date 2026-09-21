"""Quantitative measurements for experimental ultrasound phantom images."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .metrics import circular_mask, evaluate_cyst


@dataclass(frozen=True)
class PointTargetMeasurement:
    nominal_x_mm: float
    nominal_z_mm: float
    detected_x_mm: float
    detected_z_mm: float
    lateral_fwhm_mm: float
    axial_fwhm_mm: float
    position_error_mm: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


NOMINAL_POINT_TARGETS_M = (
    (0.0, 10e-3),
    (0.0, 20e-3),
    (0.0, 30e-3),
    (-10e-3, 40e-3),
    (0.0, 40e-3),
    (10e-3, 40e-3),
    (0.0, 50e-3),
)


def _half_max_width(axis: np.ndarray, profile: np.ndarray, peak_index: int) -> float:
    profile = np.asarray(profile, dtype=float)
    baseline = float(np.percentile(profile, 20.0))
    corrected = np.maximum(profile - baseline, 0.0)
    peak = float(corrected[peak_index])
    if peak <= 0:
        return float("nan")
    threshold = 0.5 * peak
    left = peak_index
    while left > 0 and corrected[left] >= threshold:
        left -= 1
    right = peak_index
    while right + 1 < corrected.size and corrected[right] >= threshold:
        right += 1
    if left == 0 or right == corrected.size - 1:
        return float("nan")

    def crossing(index_a: int, index_b: int) -> float:
        y_a, y_b = corrected[index_a], corrected[index_b]
        fraction = (threshold - y_a) / max(y_b - y_a, np.finfo(float).eps)
        return float(axis[index_a] + fraction * (axis[index_b] - axis[index_a]))

    left_crossing = crossing(left, left + 1)
    right_crossing = crossing(right, right - 1)
    return abs(right_crossing - left_crossing)


def measure_point_target(
    envelope: np.ndarray,
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
    nominal_x_m: float,
    nominal_z_m: float,
    search_radius_m: float = 4e-3,
    profile_radius_m: float = 2e-3,
) -> PointTargetMeasurement:
    """Locate a nominal point target and measure its axial/lateral -6 dB width."""
    x_indices = np.flatnonzero(np.abs(x_axis_m - nominal_x_m) <= search_radius_m)
    z_indices = np.flatnonzero(np.abs(z_axis_m - nominal_z_m) <= search_radius_m)
    if x_indices.size == 0 or z_indices.size == 0:
        raise ValueError("point-target search window does not intersect the image")
    region = envelope[np.ix_(z_indices, x_indices)]
    local_z, local_x = np.unravel_index(np.argmax(region), region.shape)
    z_index = int(z_indices[local_z])
    x_index = int(x_indices[local_x])

    lateral_indices = np.flatnonzero(np.abs(x_axis_m - x_axis_m[x_index]) <= profile_radius_m)
    axial_indices = np.flatnonzero(np.abs(z_axis_m - z_axis_m[z_index]) <= profile_radius_m)
    lateral_peak = int(np.where(lateral_indices == x_index)[0][0])
    axial_peak = int(np.where(axial_indices == z_index)[0][0])
    lateral_width = _half_max_width(
        x_axis_m[lateral_indices], envelope[z_index, lateral_indices], lateral_peak
    )
    axial_width = _half_max_width(
        z_axis_m[axial_indices], envelope[axial_indices, x_index], axial_peak
    )
    position_error = np.hypot(
        x_axis_m[x_index] - nominal_x_m,
        z_axis_m[z_index] - nominal_z_m,
    )
    return PointTargetMeasurement(
        nominal_x_mm=nominal_x_m * 1e3,
        nominal_z_mm=nominal_z_m * 1e3,
        detected_x_mm=x_axis_m[x_index] * 1e3,
        detected_z_mm=z_axis_m[z_index] * 1e3,
        lateral_fwhm_mm=lateral_width * 1e3,
        axial_fwhm_mm=axial_width * 1e3,
        position_error_mm=position_error * 1e3,
    )


def measure_resolution_phantom(
    envelope: np.ndarray,
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
) -> dict[str, object]:
    points = [
        measure_point_target(envelope, x_axis_m, z_axis_m, x, z)
        for x, z in NOMINAL_POINT_TARGETS_M
    ]
    lateral = np.array([point.lateral_fwhm_mm for point in points])
    axial = np.array([point.axial_fwhm_mm for point in points])
    errors = np.array([point.position_error_mm for point in points])
    return {
        "points": [point.to_dict() for point in points],
        "median_lateral_fwhm_mm": float(np.nanmedian(lateral)),
        "median_axial_fwhm_mm": float(np.nanmedian(axial)),
        "position_rmse_mm": float(np.sqrt(np.mean(errors**2))),
    }


def measure_contrast_phantom(
    envelope: np.ndarray,
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
) -> dict[str, object]:
    cysts = {}
    for label, depth in (("shallow_cyst", 15e-3), ("deep_cyst", 43e-3)):
        cysts[label] = evaluate_cyst(
            envelope,
            x_axis_m,
            z_axis_m,
            center_x_m=0.0,
            center_z_m=depth,
            target_radius_m=1.5e-3,
            background_inner_radius_m=2.5e-3,
            background_outer_radius_m=4.5e-3,
        ).to_dict()
    speckle_mask = circular_mask(x_axis_m, z_axis_m, 10e-3, 28e-3, 3e-3)
    speckle = np.asarray(envelope[speckle_mask], dtype=float)
    speckle_snr = float(np.mean(speckle) / max(np.std(speckle), np.finfo(float).eps))
    return {"cysts": cysts, "speckle_snr": speckle_snr}
