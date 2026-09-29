import unittest

import numpy as np

from ultrasound_bmode.ecdf_study_cli import ecdf_threshold_separation
from ultrasound_bmode.ecdf_transfer_cli import (
    directional_autocorrelation,
    evaluate_region,
    rank_binned_diagnostic,
    single_crossing_resolution_control,
)
from ultrasound_bmode.roi import LumenRoi


class EcdfTransferTests(unittest.TestCase):
    def test_rank_bins_reveal_alternating_support_and_preserve_ties(self):
        target = np.array([0, 0, 2, 2], dtype=float)
        background = np.array([1, 1, 3, 3], dtype=float)
        result = rank_binned_diagnostic(target, background, 4)
        self.assertEqual(result["rank_binned_tv"], 1)
        self.assertEqual(result["sign_changes"], 3)
        self.assertEqual(ecdf_threshold_separation(target, background), 0.5)
        self.assertEqual(result, rank_binned_diagnostic(np.exp(target),
                                                       np.exp(background), 4))
        with self.assertRaises(ValueError):
            rank_binned_diagnostic(target, background, 1)

    def test_directional_texture_detects_repeated_tiles(self):
        rng = np.random.default_rng(15)
        image = rng.rayleigh(size=(20, 20)).repeat(4, axis=0).repeat(4, axis=1)
        result = directional_autocorrelation(image, np.ones_like(image, dtype=bool),
                                              max_lag=6)
        for direction in ("axial", "lateral"):
            self.assertGreater(result[direction]["rho"][1], 0.6)
            self.assertLess(abs(result[direction]["rho"][4]), 0.2)
            self.assertGreater(result[direction]["one_over_e_crossing_pixels"], 1)
            self.assertLess(result[direction]["one_over_e_crossing_pixels"], 4)
        with self.assertRaises(ValueError):
            directional_autocorrelation(image, np.zeros_like(image, dtype=bool))

    def test_one_crossing_control_can_show_empirical_extra_signs(self):
        first = single_crossing_resolution_control(200, 300, repeats=20, seed=7)
        self.assertEqual(first, single_crossing_resolution_control(200, 300,
                                                                   repeats=20, seed=7))
        self.assertGreater(first["64"]["median"], 1)
        with self.assertRaises(ValueError):
            single_crossing_resolution_control(0, 300, repeats=20, seed=7)

    def test_fixed_roi_measurement_has_finite_summaries(self):
        axis = np.arange(80)*0.25e-3
        rng = np.random.default_rng(2)
        image = rng.rayleigh(size=(80, 80))
        roi = LumenRoi(10e-3, 10e-3, 2e-3)
        result = evaluate_region(image, axis, axis, roi,
                                 inner_offset=1e-3, outer_offset=3e-3)
        self.assertGreater(result["target_pixels"], 50)
        self.assertGreater(result["background_pixels"], 50)
        self.assertEqual([row["bins"] for row in result["rank_binned"]], [16, 32, 64])
        self.assertGreaterEqual(result["ecdf_threshold_separation"], 0)
        self.assertLessEqual(result["ecdf_threshold_separation"], 1)


if __name__ == "__main__":
    unittest.main()
