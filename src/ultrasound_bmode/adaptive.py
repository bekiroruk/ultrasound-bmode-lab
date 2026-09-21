"""Receive-aperture combination methods for adaptive ultrasound beamforming."""

from __future__ import annotations

import numpy as np


def normalized_das(samples: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted delay-and-sum over the last axis."""
    normalizer = np.sum(weights, axis=-1)
    return np.divide(
        np.sum(samples * weights, axis=-1),
        normalizer,
        out=np.zeros_like(normalizer, dtype=np.result_type(samples, float)),
        where=normalizer > 0,
    )


def coherence_factor(samples: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Return the normalized coherent-to-incoherent aperture energy ratio."""
    coherent_energy = np.abs(np.sum(samples * weights, axis=-1)) ** 2
    incoherent_energy = np.sum(weights, axis=-1) * np.sum(
        weights * np.abs(samples) ** 2, axis=-1
    )
    return np.divide(
        coherent_energy,
        incoherent_energy,
        out=np.zeros_like(coherent_energy, dtype=float),
        where=incoherent_energy > np.finfo(float).eps,
    ).clip(0.0, 1.0)


def phase_coherence_factor(samples: np.ndarray, weights: np.ndarray, power: float = 2.0) -> np.ndarray:
    """Measure phase alignment with the weighted circular resultant length."""
    unit_phase = np.exp(1j * np.angle(samples))
    normalizer = np.sum(weights, axis=-1)
    resultant = np.divide(
        np.abs(np.sum(unit_phase * weights, axis=-1)),
        normalizer,
        out=np.zeros_like(normalizer, dtype=float),
        where=normalizer > 0,
    )
    return np.clip(resultant, 0.0, 1.0) ** power


def delay_multiply_and_sum(samples: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Compute signed square-root DMAS without explicitly forming every pair."""
    weighted = np.asarray(samples.real) * np.sqrt(weights)
    transformed = np.sign(weighted) * np.sqrt(np.abs(weighted))
    pair_sum = 0.5 * (
        np.sum(transformed, axis=-1) ** 2 - np.sum(transformed**2, axis=-1)
    )
    active = np.count_nonzero(weights, axis=-1)
    pair_count = active * (active - 1) / 2
    return np.divide(
        pair_sum,
        pair_count,
        out=np.zeros_like(pair_sum, dtype=float),
        where=pair_count > 0,
    )


def mvdr_spatial_smoothing(
    samples: np.ndarray,
    weights: np.ndarray,
    subarray_size: int = 16,
    diagonal_loading: float = 0.05,
) -> complex:
    """Capon/MVDR estimate from overlapping receive-aperture subarrays.

    A single focused pixel supplies one delayed complex aperture snapshot.
    Overlapping subarrays provide spatial snapshots for covariance estimation.
    """
    active = np.flatnonzero(weights > 0)
    if active.size < 3:
        return 0.0j
    aperture = samples[active] * np.sqrt(weights[active])
    length = min(int(subarray_size), max(2, active.size // 2))
    snapshots = np.lib.stride_tricks.sliding_window_view(aperture, length)
    covariance = snapshots.conj().T @ snapshots / snapshots.shape[0]
    mean_power = float(np.trace(covariance).real / length)
    load = max(diagonal_loading * mean_power, np.finfo(float).eps)
    covariance.flat[:: length + 1] += load
    steering = np.ones(length, dtype=complex)
    solution = np.linalg.solve(covariance, steering)
    denominator = np.vdot(steering, solution)
    if abs(denominator) <= np.finfo(float).eps:
        return 0.0j
    mvdr_weights = solution / denominator
    return complex(np.vdot(mvdr_weights, np.mean(snapshots, axis=0)))
