import unittest

import numpy as np

from ultrasound_bmode.processing import envelope_detect, log_compress, time_gain_compensation


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
