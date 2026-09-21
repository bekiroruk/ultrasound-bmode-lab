import unittest

import numpy as np

from ultrasound_bmode.metrics import evaluate_cyst, evaluate_similarity


class MetricTests(unittest.TestCase):
    def test_cyst_metrics_detect_low_echo_region(self):
        x = np.linspace(-0.015, 0.015, 101)
        z = np.linspace(0.010, 0.050, 151)
        image = np.ones((z.size, x.size))
        xx, zz = np.meshgrid(x, z)
        image[(xx**2 + (zz - 0.030) ** 2) < (0.0032**2)] = 0.1
        metrics = evaluate_cyst(image, x, z)
        self.assertLess(metrics.contrast_db, -15.0)
        self.assertGreater(metrics.cnr, 1.0)
        self.assertGreaterEqual(metrics.generalized_cnr, 0.9)
        self.assertLessEqual(metrics.generalized_cnr, 1.0)

    def test_identical_images_have_perfect_similarity(self):
        image = np.linspace(-60.0, 0.0, 100).reshape(10, 10)
        metrics = evaluate_similarity(image, image.copy())
        self.assertAlmostEqual(metrics.correlation, 1.0)
        self.assertAlmostEqual(metrics.rmse_db, 0.0)
        self.assertAlmostEqual(metrics.ssim, 1.0)
        self.assertTrue(np.isinf(metrics.psnr_db))

    def test_similarity_rejects_mismatched_shapes(self):
        with self.assertRaises(ValueError):
            evaluate_similarity(np.zeros((4, 4)), np.zeros((3, 4)))
