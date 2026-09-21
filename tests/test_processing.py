import unittest

import numpy as np

from ultrasound_bmode.processing import (
    adaptive_log_compress,
    anisotropic_diffusion,
    automatic_tgc,
    envelope_detect,
    estimate_center_frequency,
    log_compress,
    suppress_common_mode,
    time_gain_compensation,
)


class ProcessingTests(unittest.TestCase):
    def test_envelope_of_sinusoid_is_nearly_constant(self):
        phase = np.linspace(0, 20 * np.pi, 2048, endpoint=False)
        rf = np.sin(phase)[:, None]
        envelope = envelope_detect(rf)
        self.assertTrue(np.allclose(envelope[100:-100], 1.0, atol=0.03))

    def test_log_compression_range_and_peak(self):
        image = np.array([[1.0, 0.1, 0.001]])
        compressed = log_compress(image, dynamic_range_db=40.0)
        self.assertTrue(np.isclose(compressed[0, 0], 0.0))
        self.assertTrue(np.isclose(compressed[0, 1], -20.0))
        self.assertEqual(compressed[0, 2], -40.0)

    def test_tgc_increases_with_depth(self):
        envelope = np.ones((3, 2))
        result = time_gain_compensation(envelope, np.array([0.0, 0.01, 0.02]), 5e6, 0.5)
        self.assertTrue(np.all(np.diff(result[:, 0]) > 0))

    def test_center_frequency_estimation_finds_rf_tone(self):
        sampling_frequency = 20e6
        time = np.arange(512) / sampling_frequency
        tone = np.sin(2 * np.pi * 5e6 * time)
        channels = np.tile(tone, (5, 8, 1))
        estimate = estimate_center_frequency(channels, sampling_frequency)
        self.assertAlmostEqual(estimate, 5e6, delta=sampling_frequency / 512)

    def test_common_mode_suppression_removes_shared_signal(self):
        data = np.ones((2, 4, 8), dtype=float)
        np.testing.assert_allclose(suppress_common_mode(data, strength=1.0), 0.0)

    def test_automatic_tgc_flattens_exponential_depth_decay(self):
        z = np.linspace(0.0, 0.05, 101)
        image = np.exp(-40.0 * z)[:, None] * np.ones((1, 8))
        compensated, gain = automatic_tgc(image, z)
        self.assertLess(np.std(np.mean(compensated, axis=1)), 0.1)
        self.assertGreater(gain[-1], gain[0])

    def test_adaptive_compression_and_diffusion_are_bounded(self):
        image = np.ones((16, 16))
        image[8, 8] = 0.01
        compressed, dynamic_range = adaptive_log_compress(image)
        diffused = anisotropic_diffusion(compressed)
        self.assertGreaterEqual(dynamic_range, 45.0)
        self.assertTrue(np.isfinite(diffused).all())
        self.assertAlmostEqual(float(anisotropic_diffusion(np.ones((8, 8))).std()), 0.0)
