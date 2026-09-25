import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.accelerated import numba_available
from ultrasound_bmode.analytic_validation_cli import (
    finite_json,
    grid_consistency,
    run_external_study,
    run_phantom_study,
)
from ultrasound_bmode.external_validation_cli import ValidationCase
from ultrasound_bmode.real_data import PlaneWaveResult, UFFAcquisition


def fixture_acquisition():
    rng = np.random.default_rng(70)
    return UFFAcquisition(
        channel_data=rng.normal(size=(75, 3, 2048)).astype(np.float32),
        sampling_frequency_hz=20e6, sound_speed_m_s=1540.0, initial_time_s=0.0,
        element_x_m=np.linspace(-1e-3, 1e-3, 3),
        transmit_angles_rad=np.linspace(-0.15, 0.15, 75),
        x_axis_m=np.linspace(-20e-3, 20e-3, 61),
        z_axis_m=np.linspace(5e-3, 55e-3, 101),
        reference_iq=rng.normal(size=(101, 61)) + 1j * rng.normal(size=(101, 61)),
        name="Synthetic offline validation fixture", citation="Not measured or clinical data",
    )


class AnalyticValidationTests(unittest.TestCase):
    def test_nonfinite_measurements_become_strict_json_null(self):
        clean = finite_json({"points": [np.nan, np.inf, -np.inf, np.float64(1.5)]})
        self.assertEqual(json.loads(json.dumps(clean, allow_nan=False)),
                         {"points": [None, None, None, 1.5]})

    def test_grid_consistency_uses_linear_envelope_and_common_normalization(self):
        signal = np.arange(1, 65).reshape(8, 8) * (1 + 1j)
        x, z = np.arange(8.0), np.arange(8.0)
        fine = PlaneWaveResult(signal, np.zeros((8, 8)), x, z, np.array([0]))
        coarse = PlaneWaveResult(signal[::2, ::2] * 2, np.zeros((4, 4)),
                                 x[::2], z[::2], np.array([0]))
        metrics = grid_consistency(fine, coarse)
        # Per-image peak normalization would incorrectly hide this factor-of-two error.
        self.assertAlmostEqual(metrics["max_absolute_difference_by_fine_peak"], 1.0)
        self.assertGreater(metrics["envelope_nrmse_by_fine_peak"], 0.1)

    def test_grid_consistency_rejects_misaligned_coordinates(self):
        fine = PlaneWaveResult(np.ones((8, 8)), np.zeros((8, 8)),
                               np.arange(8.0), np.arange(8.0), np.array([0]))
        coarse = PlaneWaveResult(np.ones((4, 4)), np.zeros((4, 4)),
                                 np.arange(4.0), np.arange(4.0), np.array([0]))
        with self.assertRaises(AssertionError):
            grid_consistency(fine, coarse)

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_external_report_keeps_same_mode_references_separate(self):
        acquisition = fixture_acquisition()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.uff"
            path.write_bytes(b"test source for checksum")
            case = ValidationCase("alpinion_phantom", "Synthetic test", path, "uff",
                                  "fixture", "fixture", "fixture", "fixture")
            with patch("ultrasound_bmode.analytic_validation_cli._cases", return_value=(case,)), \
                 patch("ultrasound_bmode.analytic_validation_cli._load", return_value=acquisition):
                report = run_external_study(root, root / "report")
            rows = report["records"]
            self.assertEqual([row["mode"] for row in rows], ["legacy", "analytic"])
            self.assertEqual(rows[1]["full_angle_count"], 75)
            self.assertLess(rows[1]["grid_consistency"]["envelope_nrmse_by_fine_peak"], 1e-12)
            self.assertGreater(rows[0]["grid_consistency"]["envelope_nrmse_by_fine_peak"], 1e-4)
            self.assertIn("No independent reference", report["reference_policy"])
            self.assertEqual(report, json.loads((root / "report/metrics.json").read_text("utf-8")))
            self.assertTrue((root / "report/alpinion_phantom.png").is_file())

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_phantom_report_retains_all_points_modes_and_matched_reference(self):
        acquisition = fixture_acquisition()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("contrast_speckle", "resolution_distortion"):
                (root / f"PICMUS_experiment_{name}.uff").write_bytes(b"test phantom source")
            with patch("ultrasound_bmode.analytic_validation_cli.load_picmus_uff",
                       return_value=acquisition):
                report = run_phantom_study(root, root / "report")
            self.assertEqual(len(report["records"]), 10)
            references = [row for row in report["records"] if row["mode"] == "embedded_reference"]
            self.assertEqual(len(references), 2)
            for row in report["records"]:
                if row["kind"] == "resolution":
                    self.assertEqual(len(row["metrics"]["points"]), 7)
                    self.assertLessEqual(row["metrics"]["valid_axial_targets"], 7)
            from ultrasound_bmode.phantom import measure_contrast_phantom

            expected = measure_contrast_phantom(
                np.abs(acquisition.reference_iq)[::2, ::2],
                acquisition.x_axis_m[::2], acquisition.z_axis_m[::2],
            )
            self.assertEqual(references[0]["metrics"], expected)
            self.assertEqual(report, json.loads((root / "report/metrics.json").read_text("utf-8")))
            self.assertEqual(len(list((root / "report").glob("*.png"))), 4)


if __name__ == "__main__":
    unittest.main()
