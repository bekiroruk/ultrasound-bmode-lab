import unittest

import numpy as np

from ultrasound_bmode.phantom import _half_max_width, measure_point_target


class PhantomMeasurementTests(unittest.TestCase):
    def test_fwhm_accepts_crossing_bracketed_by_edge_samples(self):
        width = _half_max_width(np.arange(3.0), np.array([0.0, 1.0, 0.0]), 1)
        self.assertAlmostEqual(width, 1.0)

    def test_fwhm_rejects_truncated_profile(self):
        width = _half_max_width(np.arange(4.0), np.array([0.0, 0.0, 0.8, 1.0]), 3)
        self.assertTrue(np.isnan(width))

    def test_gaussian_point_target_fwhm(self):
        x = np.linspace(-2e-3, 2e-3, 401)
        z = np.linspace(8e-3, 12e-3, 401)
        xx, zz = np.meshgrid(x, z)
        sigma_x = 0.20e-3
        sigma_z = 0.12e-3
        image = np.exp(-0.5 * ((xx / sigma_x) ** 2 + ((zz - 10e-3) / sigma_z) ** 2))
        result = measure_point_target(image, x, z, 0.0, 10e-3, search_radius_m=1e-3)
        expected_x_mm = 2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma_x * 1e3
        expected_z_mm = 2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma_z * 1e3
        self.assertAlmostEqual(result.lateral_fwhm_mm, expected_x_mm, delta=0.02)
        self.assertAlmostEqual(result.axial_fwhm_mm, expected_z_mm, delta=0.02)
        self.assertLess(result.position_error_mm, 0.02)
