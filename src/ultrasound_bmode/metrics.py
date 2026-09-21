"""Quantitative ultrasound image-quality metrics."""

from dataclasses import asdict, dataclass

import numpy as np
from scipy.ndimage import gaussian_filter


@dataclass(frozen=True)
class QualityMetrics:
    contrast_db: float
    cnr: float
    generalized_cnr: float
    target_mean: float
    background_mean: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class SimilarityMetrics:
    correlation: float
    rmse_db: float
    ssim: float
    psnr_db: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def evaluate_similarity(reference_db: np.ndarray, candidate_db: np.ndarray) -> SimilarityMetrics:
    """Compare equally sampled normalized log-compressed B-mode images."""
    reference = np.asarray(reference_db, dtype=float)
    candidate = np.asarray(candidate_db, dtype=float)
    if reference.shape != candidate.shape:
        raise ValueError("reference and candidate images must have the same shape")
    if reference.ndim != 2 or reference.size == 0:
        raise ValueError("similarity metrics require non-empty 2D images")
    if not np.isfinite(reference).all() or not np.isfinite(candidate).all():
        raise ValueError("similarity metrics require finite images")

    correlation = float(np.corrcoef(reference.ravel(), candidate.ravel())[0, 1])
    rmse_db = float(np.sqrt(np.mean((reference - candidate) ** 2)))

    # Both inputs are normalized dB images. Mapping their shared 60 dB display
    # range to [0, 1] makes SSIM and PSNR directly comparable between runs.
    low = min(float(reference.min()), float(candidate.min()), -60.0)
    high = max(float(reference.max()), float(candidate.max()), 0.0)
    scale = max(high - low, np.finfo(float).eps)
    ref_unit = np.clip((reference - low) / scale, 0.0, 1.0)
    cand_unit = np.clip((candidate - low) / scale, 0.0, 1.0)

    mu_ref = gaussian_filter(ref_unit, sigma=1.5, mode="reflect")
    mu_cand = gaussian_filter(cand_unit, sigma=1.5, mode="reflect")
    sigma_ref = gaussian_filter(ref_unit**2, sigma=1.5, mode="reflect") - mu_ref**2
    sigma_cand = gaussian_filter(cand_unit**2, sigma=1.5, mode="reflect") - mu_cand**2
    covariance = (
        gaussian_filter(ref_unit * cand_unit, sigma=1.5, mode="reflect")
        - mu_ref * mu_cand
    )
    c1 = 0.01**2
    c2 = 0.03**2
    numerator = (2.0 * mu_ref * mu_cand + c1) * (2.0 * covariance + c2)
    denominator = (mu_ref**2 + mu_cand**2 + c1) * (
        sigma_ref + sigma_cand + c2
    )
    ssim = float(np.mean(numerator / np.maximum(denominator, np.finfo(float).eps)))
    mse_unit = float(np.mean((ref_unit - cand_unit) ** 2))
    psnr_db = float("inf") if mse_unit == 0.0 else float(-10.0 * np.log10(mse_unit))
    return SimilarityMetrics(correlation, rmse_db, ssim, psnr_db)


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
