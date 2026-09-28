import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.interpolation_profile_cli import run_interpolation_profile


class InterpolationProfileTests(unittest.TestCase):
    def test_reversed_order_only_requires_same_method_repeat_parity(self):
        calls = []

        def fake_process(command, **kwargs):
            def argument(name):
                return command[command.index(name) + 1]

            count = int(argument("--count"))
            method = argument("--interpolation")
            calls.append((count, method))
            self.assertEqual(kwargs["env"]["NUMBA_NUM_THREADS"], "2")
            self.assertEqual(argument("--f-number"), "1.7")
            self.assertEqual(argument("--angle-batch-size"), "8")
            self.assertIn("--use-analytic-cache", command)
            # Distinct algorithms deliberately produce different RF and display arrays.
            signal = np.ones((2, 2)) * (1 if method == "linear" else 2)
            np.savez(argument("--result-path"), rf=signal.astype(complex), bmode=signal,
                     x_axis_m=np.arange(2), z_axis_m=np.arange(2), angle_indices=np.arange(count))
            duration = count / 10 * (1 if method == "linear" else 1.5)
            return SimpleNamespace(stdout=json.dumps({
                "angle_count": count, "interpolation": method, "numba_threads": 2,
                "median_seconds": duration, "timed_seconds": [duration, duration],
                "rss_sampled_peak_mib": 100 if method == "linear" else 110,
            }))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "source.uff"
            dataset.write_bytes(b"profile-test-input")
            with patch("ultrasound_bmode.interpolation_profile_cli.run_process",
                       side_effect=fake_process):
                report = run_interpolation_profile(dataset, root / "out", repeats=2, threads=2)
            self.assertEqual(calls[4:], calls[:4][::-1])
            self.assertEqual(len(report["repeat_parity"]), 4)
            self.assertTrue(all(row["passed"] for row in report["repeat_parity"]))
            for row in report["summaries"]:
                self.assertEqual(row["timed_call_count"], 4)
                self.assertEqual(row["process_count"], 2)
            for row in report["comparisons"]:
                self.assertAlmostEqual(row["cubic_time_increase_percent"], 50)
                self.assertEqual(row["cubic_peak_rss_increase_mib"], 10)
            self.assertEqual(report, json.loads((root / "out/metrics.json").read_text("utf-8")))

    def test_rejects_invalid_protocol_before_loading(self):
        for kwargs in ({"repeats": 1}, {"repeats": True}, {"threads": 0}, {"threads": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_interpolation_profile(Path("missing.uff"), Path("unused"), **kwargs)

    def test_repeat_parity_rejects_geometry_or_signal_drift(self):
        from ultrasound_bmode.interpolation_profile_cli import _check_repeat

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = {"rf": np.ones((2, 2), complex), "bmode": np.zeros((2, 2)),
                    "x_axis_m": np.arange(2), "z_axis_m": np.arange(2),
                    "angle_indices": np.array([0, 1])}
            np.savez(root / "base.npz", **base)
            for key, value in base.items():
                changed = dict(base)
                changed[key] = value + 1
                np.savez(root / "changed.npz", **changed)
                with self.subTest(key=key), self.assertRaises(AssertionError):
                    _check_repeat(root / "base.npz", root / "changed.npz")


if __name__ == "__main__":
    unittest.main()
