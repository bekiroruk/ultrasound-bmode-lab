import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.cache_profile_cli import run_cache_profile


class CacheProfileReportTests(unittest.TestCase):
    def test_profile_pairs_cached_and_uncached_outputs(self):
        def processor_probe():
            return subprocess.check_output(
                [sys.executable, "-c", "print('cache-test-cpu')"], text=True
            ).strip()

        def fake_subprocess(command, **kwargs):
            count = int(command[command.index("--count") + 1])
            cached = "--use-analytic-cache" in command
            path = command[command.index("--result-path") + 1]
            np.savez(path, rf=np.ones((2, 2), complex) * count,
                     bmode=np.ones((2, 2)) * count)
            median = 0.8 if cached else 1.0
            row = {
                "angle_count": count, "analytic_cache": cached,
                "median_seconds": median, "minimum_seconds": median - 0.1,
                "maximum_seconds": median + 0.1, "median_fps": 1 / median,
                "rss_baseline_mib": 150 if cached else 100,
                "rss_sampled_peak_mib": 170 if cached else 120,
                "analytic_cache_preparation_seconds": 0.3 if cached else None,
                "analytic_cache_mib": 56.25 if cached else 0.0,
            }
            return SimpleNamespace(stdout=json.dumps(row))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.uff"
            source.write_bytes(b"synthetic cache profile source")
            with patch("ultrasound_bmode.cache_profile_cli.run_process",
                       side_effect=fake_subprocess) as runner, \
                 patch("ultrasound_bmode.cache_profile_cli.platform.processor",
                       side_effect=processor_probe):
                report = run_cache_profile(source, root / "report", repeats=3)

            self.assertEqual(runner.call_count, 4)
            self.assertEqual(report["processor"], "cache-test-cpu")
            self.assertEqual([row["angle_count"] for row in report["comparisons"]], [11, 75])
            self.assertTrue(all(row["passed"] for row in report["parity"]))
            for row in report["comparisons"]:
                self.assertAlmostEqual(row["repeated_call_time_reduction_percent"], 20)
                self.assertEqual(row["sampled_peak_rss_increase_mib"], 50)
                self.assertEqual(row["break_even_reconstruction_count"], 2)
            self.assertTrue((root / "report/cache_profile.png").is_file())
            self.assertEqual(report, json.loads(
                (root / "report/metrics.json").read_text(encoding="utf-8")
            ))

    def test_profile_requires_repeated_measurements(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            run_cache_profile(Path("unused.uff"), Path("unused"), repeats=1)


if __name__ == "__main__":
    unittest.main()
