import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ultrasound_bmode.coverage_cli import rayleigh_truth
from ultrasound_bmode.ecdf_study_cli import (
    dkw_interval,
    ecdf_threshold_separation,
    roi_samples,
    run_study,
)
from ultrasound_bmode.rayleigh_coverage_cli import _draw_field


class EcdfStudyTests(unittest.TestCase):
    def test_ties_and_monotone_invariance(self):
        a = np.array([0, 0, 1, 1, 3], dtype=float)
        b = np.array([0, 2, 2, 3, 3], dtype=float)
        first = ecdf_threshold_separation(a, b)
        self.assertAlmostEqual(first, 0.6)
        self.assertAlmostEqual(first, ecdf_threshold_separation(np.exp(a), np.exp(b)))
        self.assertEqual(0, ecdf_threshold_separation(a, a))
        with self.assertRaises(ValueError):
            ecdf_threshold_separation([np.nan], [1])

    def test_multicrossing_is_not_general_gcnr(self):
        # Disjoint supports have density-overlap gCNR=1, but a single threshold
        # cannot separate alternating point masses perfectly.
        self.assertEqual(ecdf_threshold_separation([0, 2], [1, 3]), 0.5)

    def test_large_iid_sample_approaches_one_crossing_truth(self):
        rng = np.random.default_rng(12)
        target = rng.rayleigh(scale=0.5, size=100_000)
        background = rng.rayleigh(scale=1, size=100_000)
        self.assertLess(abs(ecdf_threshold_separation(target, background)
                            - rayleigh_truth()["generalized_cnr"]), 0.01)

    def test_source_cell_selection_reduces_correlated_count(self):
        field, axis, roi = _draw_field(np.random.default_rng(7),
                                       "offset_correlated_rayleigh")
        pixels = roi_samples(field, axis, roi)
        cells = roi_samples(field, axis, roi, tile_side=4, tile_origin=2)
        for full, unique in zip(pixels, cells, strict=True):
            self.assertLess(unique.size, full.size)
            self.assertGreater(unique.size, 1)

    def test_dkw_interval_validation_and_radius(self):
        self.assertEqual(dkw_interval(0.5, 1, 1), [0.0, 1.0])
        interval = dkw_interval(0.5, 1000, 1000)
        radius = 4*math.sqrt(math.log(80)/2000)
        self.assertAlmostEqual(interval[0], 0.5-radius)
        self.assertAlmostEqual(interval[1], 0.5+radius)
        with self.assertRaises(ValueError):
            dkw_interval(0.5, 0, 10)

    def test_smoke_report_without_measured_data(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run_study(Path(directory), trials=2, seed=4)
            self.assertEqual(len(report["summaries"]), 4)
            self.assertEqual(len(report["records"]), 8)
            self.assertTrue((Path(directory) / "comparison.png").is_file())
            self.assertTrue((Path(directory) / "metrics.json").is_file())


if __name__ == "__main__":
    unittest.main()
