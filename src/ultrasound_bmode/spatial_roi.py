"""Paired non-overlapping spatial-tile resampling on a fixed carotid ROI."""

from __future__ import annotations

from numbers import Integral

import numpy as np

from .metrics import _generalized_cnr, circular_mask
from .roi import LumenRoi

METRICS = ("contrast_db", "cnr", "generalized_cnr")


def _positive_integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _statistics(target, background):
    eps = np.finfo(float).eps
    target_mean, background_mean = np.mean(target), np.mean(background)
    return np.array([
        20 * np.log10((target_mean + eps) / (background_mean + eps)),
        abs(background_mean - target_mean)
        / np.sqrt(np.var(target) + np.var(background) + eps),
        _generalized_cnr(target, background),
    ])


def _intervals(point, draws):
    return {
        name: {"estimate": float(point[index]),
               "percentile95": np.percentile(draws[:, index], [2.5, 97.5]).tolist()}
        for index, name in enumerate(METRICS)
    }


def paired_spatial_bootstrap(
    envelopes: dict[str, np.ndarray],
    x_axis_m: np.ndarray,
    z_axis_m: np.ndarray,
    roi: LumenRoi,
    *,
    block_size: int = 8,
    samples: int = 500,
    seed: int = 7,
    comparisons: tuple[tuple[str, str], ...] = (),
    block_origin: tuple[int, int] = (0, 0),
) -> dict:
    """Resample occupied tiles jointly across images; report first-minus-second deltas.

    Tiles are anchored at block_origin in (row, column) pixels. All masked pixels of a tile
    move together, including target/background pixels if both occur in that tile.
    Boundary tiles retain partial masks and replicate pixel counts may vary.
    These conditional percentile intervals have no established coverage guarantee.
    """
    _positive_integer(block_size, "block_size")
    _positive_integer(samples, "samples", 20)
    _positive_integer(seed, "seed", 0)
    if not isinstance(block_origin, (tuple, list)) or len(block_origin) != 2:
        raise ValueError("block_origin must contain axial and lateral integer offsets")
    for offset in block_origin:
        _positive_integer(offset, "block_origin", 0)
        if offset >= block_size:
            raise ValueError("block_origin offsets must be less than block_size")
    x, z = np.asarray(x_axis_m), np.asarray(z_axis_m)
    for axis in (x, z):
        if (axis.ndim != 1 or axis.size < 2 or not np.isfinite(axis).all()
                or np.any(np.diff(axis) <= 0)
                # UFF coordinates can retain float32 quantization after float64 loading.
                or not np.allclose(np.diff(axis), np.mean(np.diff(axis)),
                                   rtol=1e-4, atol=1e-12)):
            raise ValueError("axes must be finite, increasing, uniformly spaced 1D arrays")
    if (not np.isfinite([roi.center_x_m, roi.center_z_m, roi.radius_m]).all()
            or roi.radius_m <= 0):
        raise ValueError("ROI must be finite with positive radius")
    outer_radius = roi.radius_m + 3e-3
    if (roi.center_x_m - outer_radius < x[0] or roi.center_x_m + outer_radius > x[-1]
            or roi.center_z_m - outer_radius < z[0]
            or roi.center_z_m + outer_radius > z[-1]):
        raise ValueError("complete target and background annulus must fit within the grid")
    if not envelopes:
        raise ValueError("at least one envelope is required")
    for name, envelope in envelopes.items():
        image = np.asarray(envelope)
        if (image.shape != (z.size, x.size) or np.iscomplexobj(image)
                or not np.isfinite(image).all() or np.any(image < 0)):
            raise ValueError(f"{name}: expected a finite nonnegative real envelope on the grid")
    for first, second in comparisons:
        if first not in envelopes or second not in envelopes:
            raise ValueError("comparison names must identify provided envelopes")

    target = circular_mask(x, z, roi.center_x_m, roi.center_z_m, roi.radius_m)
    background = circular_mask(x, z, roi.center_x_m, roi.center_z_m, outer_radius)
    background &= ~circular_mask(x, z, roi.center_x_m, roi.center_z_m, roi.radius_m + 1e-3)
    union = target | background
    rows, columns = np.nonzero(union)
    # Coordinate pairs avoid collisions when shifted edge tiles have negative indices.
    tiles = np.column_stack(((rows - block_origin[0]) // block_size,
                             (columns - block_origin[1]) // block_size))
    _, labels = np.unique(tiles, axis=0, return_inverse=True)
    is_target = target[union]
    target_blocks = np.unique(labels[is_target]).size
    background_blocks = np.unique(labels[~is_target]).size
    if min(target_blocks, background_blocks) < 4:
        raise ValueError("at least four occupied blocks in each ROI are required")
    block_count = int(labels.max() + 1)
    arrays = {name: np.asarray(image, dtype=float)[union] for name, image in envelopes.items()}
    points = {name: _statistics(values[is_target], values[~is_target])
              for name, values in arrays.items()}
    draws = {name: np.empty((samples, 3)) for name in arrays}
    rng = np.random.default_rng(seed)
    accepted, rejected = 0, 0
    pixel_counts = []
    while accepted < samples:
        multiplicities = np.bincount(rng.integers(block_count, size=block_count),
                                    minlength=block_count)
        indices = np.repeat(np.arange(labels.size), multiplicities[labels])
        selected_target = is_target[indices]
        n_target = int(np.sum(selected_target))
        n_background = int(indices.size - n_target)
        if min(n_target, n_background) < 2:
            rejected += 1
            if rejected > 20 * samples:
                raise ValueError("too many resamples with insufficient ROI support")
            continue
        for name, values in arrays.items():
            selected = values[indices]
            draws[name][accepted] = _statistics(
                selected[selected_target], selected[~selected_target]
            )
        pixel_counts.append((n_target, n_background))
        accepted += 1
    return {
        "method": "paired non-overlapping occupied-tile percentile bootstrap",
        "gcnr_estimator": (
            "64-bin histogram overlap; shared target/background min-max edges recomputed "
            "for each image and replicate, matching the existing point estimator. "
            "Histogram-bin and finite-sample bias sensitivity are not calibrated."
        ),
        "block_size_pixels": [int(block_size), int(block_size)],
        "block_size_mm": [float(block_size * np.mean(np.diff(z)) * 1e3),
                          float(block_size * np.mean(np.diff(x)) * 1e3)],
        "grid_uniformity_rtol": 1e-4,
        "grid_anchor_pixels": [int(value) for value in block_origin],
        "seed": int(seed), "samples": int(samples),
        "occupied_blocks": block_count, "target_blocks": int(target_blocks),
        "background_blocks": int(background_blocks),
        "target_pixels": int(is_target.sum()), "background_pixels": int((~is_target).sum()),
        "rejected_insufficient_support_draws": rejected,
        "replicate_pixel_count_min_max": {
            "target": [min(v[0] for v in pixel_counts), max(v[0] for v in pixel_counts)],
            "background": [min(v[1] for v in pixel_counts), max(v[1] for v in pixel_counts)],
        },
        "images": {name: _intervals(points[name], values) for name, values in draws.items()},
        "paired_differences": [
            {"first": first, "second": second,
             "metrics": _intervals(points[first] - points[second], draws[first] - draws[second])}
            for first, second in comparisons
        ],
        "limitations": (
            "Fixed ROI, fixed grid origin and one acquisition; partial tiles retain their masks. "
            "Pixel counts vary across replicates. Dependence within tiles is retained, dependence "
            "between tiles is not. Resamples lacking either ROI are rejected and counted. "
            "Block sizes are sensitivity settings, not estimated correlation lengths. "
            "No calibrated 95% coverage, ROI-selection, registration, inter-subject or clinical "
            "uncertainty claim. At least four blocks per ROI is a guard, not a sufficiency proof."
        ),
    }
