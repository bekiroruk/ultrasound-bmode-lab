"""Registration and uncertainty-aware carotid region-of-interest analysis."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter

from .metrics import _generalized_cnr, circular_mask, evaluate_cyst


@dataclass(frozen=True)
class LumenRoi:
    center_x_m: float
    center_z_m: float
    radius_m: float


def estimate_translation(reference: np.ndarray, candidate: np.ndarray) -> tuple[float, float]:
    """Estimate the pixel shift that aligns candidate to reference by phase correlation."""
    if reference.shape != candidate.shape or reference.ndim != 2:
        raise ValueError("registration requires equally shaped 2D images")
    reference_zero_mean = reference - np.mean(reference)
    candidate_zero_mean = candidate - np.mean(candidate)
    cross_power = np.fft.fft2(reference_zero_mean) * np.conj(
        np.fft.fft2(candidate_zero_mean)
    )
    cross_power /= np.maximum(np.abs(cross_power), np.finfo(float).eps)
    correlation = np.abs(np.fft.ifft2(cross_power))
    peak = np.array(np.unravel_index(np.argmax(correlation), correlation.shape), dtype=float)
    for dimension, size in enumerate(reference.shape):
        if peak[dimension] > size // 2:
            peak[dimension] -= size
    return float(peak[0]), float(peak[1])


def locate_carotid_lumen(
    bmode_db: np.ndarray,
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
    radius_m: float = 2.2e-3,
) -> LumenRoi:
    """Locate the darkest smoothed region in the expected carotid lumen window."""
    x_indices = np.flatnonzero((x_axis_m >= -5e-3) & (x_axis_m <= 5e-3))
    z_indices = np.flatnonzero((z_axis_m >= 14e-3) & (z_axis_m <= 23e-3))
    if x_indices.size == 0 or z_indices.size == 0:
        raise ValueError("carotid search region does not intersect the image")
    smoothed = gaussian_filter(np.asarray(bmode_db, dtype=float), sigma=2.0)
    region = smoothed[np.ix_(z_indices, x_indices)]
    local_z, local_x = np.unravel_index(np.argmin(region), region.shape)
    return LumenRoi(
        center_x_m=float(x_axis_m[x_indices[local_x]]),
        center_z_m=float(z_axis_m[z_indices[local_z]]),
        radius_m=radius_m,
    )


def bootstrap_cyst_metrics(
    envelope: np.ndarray,
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
    roi: LumenRoi,
    samples: int = 500,
    seed: int = 7,
) -> dict[str, object]:
    """Return lumen metrics with percentile bootstrap confidence intervals."""
    target_mask = circular_mask(
        x_axis_m, z_axis_m, roi.center_x_m, roi.center_z_m, roi.radius_m
    )
    outer = circular_mask(
        x_axis_m, z_axis_m, roi.center_x_m, roi.center_z_m, roi.radius_m + 3.0e-3
    )
    inner = circular_mask(
        x_axis_m, z_axis_m, roi.center_x_m, roi.center_z_m, roi.radius_m + 1.0e-3
    )
    target = np.asarray(envelope[target_mask], dtype=float)
    background = np.asarray(envelope[outer & ~inner], dtype=float)
    if target.size < 2 or background.size < 2:
        raise ValueError("ROI contains too few samples for uncertainty estimation")
    point = evaluate_cyst(
        envelope,
        x_axis_m,
        z_axis_m,
        center_x_m=roi.center_x_m,
        center_z_m=roi.center_z_m,
        target_radius_m=roi.radius_m,
        background_inner_radius_m=roi.radius_m + 1.0e-3,
        background_outer_radius_m=roi.radius_m + 3.0e-3,
    )
    rng = np.random.default_rng(seed)
    values = np.zeros((samples, 3), dtype=float)
    eps = np.finfo(float).eps
    for index in range(samples):
        target_sample = rng.choice(target, target.size, replace=True)
        background_sample = rng.choice(background, background.size, replace=True)
        target_mean = float(np.mean(target_sample))
        background_mean = float(np.mean(background_sample))
        values[index, 0] = 20.0 * np.log10(
            (target_mean + eps) / (background_mean + eps)
        )
        values[index, 1] = abs(background_mean - target_mean) / np.sqrt(
            np.var(background_sample) + np.var(target_sample) + eps
        )
        values[index, 2] = _generalized_cnr(target_sample, background_sample)
    names = ("contrast_db", "cnr", "generalized_cnr")
    point_values = (point.contrast_db, point.cnr, point.generalized_cnr)
    return {
        name: {
            "estimate": float(estimate),
            "ci95": [
                float(np.percentile(values[:, metric_index], 2.5)),
                float(np.percentile(values[:, metric_index], 97.5)),
            ],
        }
        for metric_index, (name, estimate) in enumerate(zip(names, point_values, strict=True))
    }


def wall_edge_sharpness(
    bmode_db: np.ndarray,
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
    roi: LumenRoi,
) -> float:
    """Measure median gradient magnitude in a one-millimetre lumen-wall ring."""
    dz = float(np.mean(np.diff(z_axis_m))) * 1e3
    dx = float(np.mean(np.diff(x_axis_m))) * 1e3
    gradient_z, gradient_x = np.gradient(bmode_db, dz, dx)
    magnitude = np.hypot(gradient_x, gradient_z)
    outer = circular_mask(
        x_axis_m, z_axis_m, roi.center_x_m, roi.center_z_m, roi.radius_m + 0.5e-3
    )
    inner = circular_mask(
        x_axis_m, z_axis_m, roi.center_x_m, roi.center_z_m, roi.radius_m - 0.5e-3
    )
    return float(np.median(magnitude[outer & ~inner]))
