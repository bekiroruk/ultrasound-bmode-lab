"""Quantitative ultrasound image-quality metrics."""

from dataclasses import dataclass, asdict

import numpy as np


@dataclass(frozen=True)
class QualityMetrics:
    contrast_db: float
    cnr: float
    generalized_cnr: float
    target_mean: float
    background_mean: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def circular_mask(
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
    center_x_m: float,
    center_z_m: float,
    radius_m: float,
) -> np.ndarray:
    xx, zz = np.meshgrid(x_axis_m, z_axis_m)
    return (xx - center_x_m) ** 2 + (zz - center_z_m) ** 2 <= radius_m**2


def _generalized_cnr(target: np.ndarray, background: np.ndarray, bins: int = 64) -> float:
    values = np.concatenate([target, background])
    low, high = float(values.min()), float(values.max())
    if np.isclose(low, high):
        return 0.0
    target_hist, edges = np.histogram(target, bins=bins, range=(low, high), density=True)
    background_hist, _ = np.histogram(background, bins=edges, density=True)
    bin_width = edges[1] - edges[0]
    overlap = np.sum(np.minimum(target_hist, background_hist)) * bin_width
    return float(np.clip(1.0 - overlap, 0.0, 1.0))


def evaluate_cyst(
    envelope: np.ndarray,
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
    center_x_m: float = 0.0,
    center_z_m: float = 30e-3,
    target_radius_m: float = 3.2e-3,
    background_inner_radius_m: float = 5.0e-3,
    background_outer_radius_m: float = 8.0e-3,
) -> QualityMetrics:
    """Measure contrast, CNR, and histogram-overlap gCNR for a cyst ROI."""
    target_mask = circular_mask(
        x_axis_m, z_axis_m, center_x_m, center_z_m, target_radius_m
    )
    outer = circular_mask(
        x_axis_m, z_axis_m, center_x_m, center_z_m, background_outer_radius_m
    )
    inner = circular_mask(
        x_axis_m, z_axis_m, center_x_m, center_z_m, background_inner_radius_m
    )
    background_mask = outer & ~inner
    target = np.asarray(envelope[target_mask], dtype=float)
    background = np.asarray(envelope[background_mask], dtype=float)
    if target.size == 0 or background.size == 0:
        raise ValueError("ROI does not intersect the image grid")

    target_mean = float(np.mean(target))
    background_mean = float(np.mean(background))
    eps = np.finfo(float).eps
    contrast_db = 20.0 * np.log10((target_mean + eps) / (background_mean + eps))
    cnr = abs(background_mean - target_mean) / np.sqrt(
        np.var(background) + np.var(target) + eps
    )
    return QualityMetrics(
        contrast_db=float(contrast_db),
        cnr=float(cnr),
        generalized_cnr=_generalized_cnr(target, background),
        target_mean=target_mean,
        background_mean=background_mean,
    )

