import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.accelerated import numba_available
from ultrasound_bmode.native_profile_cli import agreement
from ultrasound_bmode.sequence import UFFPlaneWaveSequence
from ultrasound_bmode.sequence_cli import run_sequence


class FinalReportTests(unittest.TestCase):
    def test_agreement_rejects_changed_rf_and_display(self):
        expected = {"rf": np.ones((2, 3), dtype=complex), "bmode": np.zeros((2, 3))}
        self.assertTrue(agreement(expected, expected)["passed"])
        for key in expected:
            actual = {name: value.copy() for name, value in expected.items()}
            actual[key][0, 0] += 1
            with self.subTest(key=key), self.assertRaises(AssertionError):
                agreement(actual, expected)

    def test_portfolio_has_offline_figures_and_tabs(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("portfolio", root / "scripts/build_portfolio.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # A temporary project uses tiny image placeholders; parsing, not image rendering, is tested.
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for relative in ("sequence/metrics.json", "native_profile/metrics.json",
                             "coverage/metrics.json"):
                path = target / "artifacts" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((root / "artifacts" / relative).read_bytes())
            for relative in ("analytic_quality/PICMUS_carotid_cross_75_angles.png",
                             "interpolation_study/contrast_interpolation.png",
                             "coverage/coverage.png", "sequence/frames.png",
                             "sequence/profile.png", "native_profile/profile.png"):
                path = target / "artifacts" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"test-image")
            page = module.build_portfolio(target).read_text(encoding="utf-8")
            self.assertEqual(page.count('role="tab"'), 6)
            self.assertEqual(page.count('role="tabpanel"'), 6)
            self.assertEqual(page.count("data:image/png;base64,"), 6)
            self.assertNotIn('<img src="http', page)

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_sequence_report_with_small_generated_uff(self):
        # Standalone fixture, no network or public dataset needed.
        import h5py

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "sequence.uff"
            with h5py.File(path, "w") as f:
                g = f.create_group("channel_data")
                g["data"] = np.random.default_rng(7).normal(size=(3, 1, 2, 128)).astype("float32")
                for key, value in {
                    "sampling_frequency": 1e6, "sound_speed": 1540, "initial_time": 0,
                    "modulation_frequency": 0, "sequence/delay": -1e-6,
                    "sequence/source/azimuth": 0, "sequence/source/distance": np.inf,
                    "sequence/source/elevation": 0, "sequence/sound_speed": 1540,
                }.items():
                    g[key] = np.array([[value]], dtype=float)
                g["probe/geometry"] = [[-0.001, 0.001], [0, 0], [0, 0]]
            with patch("ultrasound_bmode.sequence_cli.UFFPlaneWaveSequence",
                       side_effect=lambda path: UFFPlaneWaveSequence(path, 4, 8)):
                report = run_sequence(path, root / "report")
            self.assertEqual(report["frame_count"], 3)
            self.assertEqual(len(report["latency_ms"]), 3)
            self.assertEqual(len(report["numpy_checkpoint_agreement"]), 3)
            self.assertIsNone(report["acquisition_frame_rate_hz"])
            self.assertTrue((root / "report/frames.png").is_file())
            persisted = json.loads((root / "report/metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["effective_initial_time_s"], -1e-6)
