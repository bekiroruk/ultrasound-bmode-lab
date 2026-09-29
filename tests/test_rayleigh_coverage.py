import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.stats import rayleigh

from ultrasound_bmode.coverage_cli import draw_envelope
from ultrasound_bmode.rayleigh_coverage_cli import (
    rayleigh_mle_gcnr,
    rayleigh_overlap_gcnr,
    run_study,
    tile_interval,
)


class RayleighCoverageTests(unittest.TestCase):
    def test_population_overlap_matches_numerical_integration(self):
        for a, b in ((0.5, 1), (1, 0.5), (0.8, 0.8), (1, 3)):
            with self.subTest(a=a, b=b):
                overlap = quad(lambda x, p=a, q=b: min(rayleigh.pdf(x, scale=p),
                                                       rayleigh.pdf(x, scale=q)), 0, 30)[0]
                self.assertAlmostEqual(rayleigh_overlap_gcnr(a, b), 1-overlap, places=7)
        self.assertEqual(rayleigh_overlap_gcnr(1, 1), 0)
        with self.assertRaises(ValueError):
            rayleigh_overlap_gcnr(0, 1)

    def test_mle_large_samples_approach_truth_and_scale_invariant(self):
        rng = np.random.default_rng(4)
        target = rng.rayleigh(scale=0.5, size=100_000)
        background = rng.rayleigh(scale=1, size=100_000)
        value = rayleigh_mle_gcnr(target, background)
        self.assertLess(abs(value-rayleigh_overlap_gcnr(0.5, 1)), 0.01)
        self.assertAlmostEqual(value, rayleigh_mle_gcnr(3*target, 3*background), places=12)
        with self.assertRaises(ValueError):
            rayleigh_mle_gcnr([0, np.nan], [1, 2])

    def test_tiling_seed_and_smoke(self):
        field, axis, roi = draw_envelope(np.random.default_rng(8), correlated=True)
        first = tile_interval(field, axis, roi, block_size=8, origin=2, samples=20, seed=5)
        second = tile_interval(field, axis, roi, block_size=8, origin=2, samples=20, seed=5)
        self.assertEqual(first, second)
        self.assertLessEqual(first["percentile95"][0], first["percentile95"][1])
        self.assertLessEqual(first["basic95"][0], first["basic95"][1])
        self.assertAlmostEqual(first["basic95"][0],
                               max(0, 2*first["estimate"]-first["percentile95"][1]))
        with self.assertRaises(ValueError):
            tile_interval(field, axis, roi, block_size=8, origin=8, samples=20, seed=5)
        with tempfile.TemporaryDirectory() as directory:
            report = run_study(Path(directory), trials=2, samples=20)
            self.assertEqual(len(report["records"]), 14)
            self.assertEqual(len(report["summaries"]), 7)
            self.assertTrue(all(0 <= row["basic_coverage"] <= 1
                                for row in report["summaries"]))
            self.assertTrue((Path(directory) / "coverage.png").is_file())
            self.assertAlmostEqual(report["truth"]["iid_lognormal_stress"],
                                   math.erf(math.log(2)/(2*math.sqrt(2)*0.7)))
