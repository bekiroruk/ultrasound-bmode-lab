import unittest

import numpy as np

from ultrasound_bmode.adaptive import (
    coherence_factor,
    delay_multiply_and_sum,
    mvdr_spatial_smoothing,
    normalized_das,
    phase_coherence_factor,
)


class AdaptiveBeamformingTests(unittest.TestCase):
    def test_coherent_aperture_has_unit_coherence(self):
        samples = np.ones((3, 8), dtype=complex)
        weights = np.ones_like(samples.real)
        np.testing.assert_allclose(coherence_factor(samples, weights), 1.0)
        np.testing.assert_allclose(phase_coherence_factor(samples, weights), 1.0)

    def test_incoherent_phase_is_suppressed(self):
        phases = np.linspace(0.0, 2.0 * np.pi, 8, endpoint=False)
        samples = np.exp(1j * phases)[None, :]
        weights = np.ones_like(samples.real)
        self.assertLess(float(coherence_factor(samples, weights)[0]), 1e-12)
        self.assertLess(float(phase_coherence_factor(samples, weights)[0]), 1e-12)

    def test_dmas_pair_identity_for_equal_samples(self):
        samples = np.full((1, 4), 4.0)
        weights = np.ones_like(samples)
        np.testing.assert_allclose(delay_multiply_and_sum(samples, weights), 4.0)

    def test_normalized_das_respects_weights(self):
        samples = np.array([[1.0, 3.0]])
        weights = np.array([[1.0, 0.0]])
        np.testing.assert_allclose(normalized_das(samples, weights), 1.0)

    def test_mvdr_returns_finite_complex_value(self):
        samples = np.exp(1j * np.linspace(-0.1, 0.1, 16))
        value = mvdr_spatial_smoothing(samples, np.ones(16), subarray_size=8)
        self.assertTrue(np.isfinite(value.real))
        self.assertTrue(np.isfinite(value.imag))
