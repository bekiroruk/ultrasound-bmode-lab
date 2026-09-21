import unittest

import numpy as np
from scipy.ndimage import shift

from ultrasound_bmode.roi import LumenRoi, bootstrap_cyst_metrics, estimate_translation


class RoiAnalysisTests(unittest.TestCase):
    def test_phase_correlation_recovers_integer_shift(self):
        reference = np.zeros((64, 64))
        reference[20:30, 25:35] = 1.0
        candidate = shift(reference, (3, -4), order=0, mode="wrap")
        estimated = estimate_translation(reference, candidate)
        self.assertEqual(estimated, (-3.0, 4.0))

    def test_bootstrap_metrics_are_deterministic(self):
        x = np.linspace(-0.01, 0.01, 61)
        z = np.linspace(0.01, 0.03, 61)
        image = np.ones((61, 61))
        xx, zz = np.meshgrid(x, z)
        image[(xx**2 + (zz - 0.02) ** 2) <= (0.002**2)] = 0.2
        roi = LumenRoi(0.0, 0.02, 0.002)
        first = bootstrap_cyst_metrics(image, x, z, roi, samples=30, seed=3)
        second = bootstrap_cyst_metrics(image, x, z, roi, samples=30, seed=3)
        self.assertEqual(first, second)
        self.assertLess(first["contrast_db"]["estimate"], 0.0)
