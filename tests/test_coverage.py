import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.stats import rayleigh

from ultrasound_bmode.coverage_cli import (
    draw_envelope,
    rayleigh_truth,
    run_coverage,
    wilson_interval,
)


class CoverageTests(unittest.TestCase):
    def test_known_metrics_against_distribution_integrals(self):
        truth = rayleigh_truth()
        target, background = rayleigh(scale=0.5), rayleigh(scale=1)
        overlap = quad(lambda x: min(target.pdf(x), background.pdf(x)), 0, 12)[0]
        self.assertAlmostEqual(truth["generalized_cnr"], 1 - overlap, places=7)
        self.assertAlmostEqual(truth["cnr"], abs(target.mean()-background.mean())
                               / np.sqrt(target.var()+background.var()))
        self.assertAlmostEqual(truth["contrast_db"],
                               20*np.log10(target.mean()/background.mean()))
        with self.assertRaises(ValueError):
            rayleigh_truth(1, 0.5)

    def test_wilson_and_seeded_fields(self):
        self.assertAlmostEqual(wilson_interval(0, 200)[0], 0)
        self.assertGreater(wilson_interval(0, 200)[1], 0)
        self.assertAlmostEqual(wilson_interval(200, 200)[1], 1)
        with self.assertRaises(ValueError):
            wilson_interval(2, 1)
        for correlated in (False, True):
            a, _, _ = draw_envelope(np.random.default_rng(42), correlated)
            b, _, _ = draw_envelope(np.random.default_rng(42), correlated)
            np.testing.assert_array_equal(a, b)
            self.assertTrue(np.isfinite(a).all())

    def test_report_smoke(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_coverage(Path(directory), trials=2, samples=20)
            self.assertEqual(len(result["records"]), 12)
            self.assertEqual(len(result["summaries"]), 18)
            self.assertTrue((Path(directory) / "coverage.png").is_file())
            self.assertTrue(all(0 <= r["coverage"] <= 1 for r in result["summaries"]))
