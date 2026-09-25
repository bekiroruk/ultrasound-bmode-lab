import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.accelerated import numba_available
from ultrasound_bmode.aperture_transfer_cli import compare_reconstructions, run_transfer
from ultrasound_bmode.batch_profile_cli import run_batch_profile
from ultrasound_bmode.external_validation_cli import ValidationCase
from ultrasound_bmode.real_data import PlaneWaveResult, UFFAcquisition


class TransferParityTests(unittest.TestCase):
    def test_parity_reports_full_array_error(self):
        result = PlaneWaveResult(np.ones((3, 3), dtype=complex), np.zeros((3, 3)),
                                 np.arange(3), np.arange(3), np.array([0, 2, 1]))
        report = compare_reconstructions(result, result)
        self.assertTrue(report["passed"])
        self.assertEqual(report["rf_max_absolute_error"], 0)

    def test_parity_rejects_geometry_order_or_signal_change(self):
        result = PlaneWaveResult(np.ones((3, 3), dtype=complex), np.zeros((3, 3)),
                                 np.arange(3), np.arange(3), np.array([0, 2, 1]))
        for changed in (replace(result, x_axis_m=np.arange(3) + 1),
                        replace(result, angle_indices=np.array([0, 1, 2])),
                        replace(result, rf=result.rf * 2),
                        replace(result, bmode_db=np.ones((3, 3)))):
            with self.assertRaises(AssertionError):
                compare_reconstructions(result, changed)

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_frozen_transfer_report_keeps_reference_type_and_both_apertures(self):
        rng = np.random.default_rng(90)
        acquisition = UFFAcquisition(
            channel_data=rng.normal(size=(13, 3, 768)).astype(np.float32),
            sampling_frequency_hz=20e6, sound_speed_m_s=1540, initial_time_s=0,
            element_x_m=np.linspace(-1e-3, 1e-3, 3),
            transmit_angles_rad=np.linspace(-0.2, 0.2, 13),
            x_axis_m=np.linspace(-2e-3, 2e-3, 9), z_axis_m=np.linspace(5e-3, 25e-3, 30),
            reference_iq=rng.normal(size=(30, 9)) + 1j * rng.normal(size=(30, 9)),
            name="Synthetic transfer test", citation="Not measured data",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.uff"
            path.write_bytes(b"test source")
            case = ValidationCase("picmus_cross", "Test", path, "uff", "Test", "Test", "Test", "Test")
            with patch("ultrasound_bmode.aperture_transfer_cli._cases", return_value=(case,)), \
                 patch("ultrasound_bmode.aperture_transfer_cli._load", return_value=acquisition):
                report = run_transfer(root, root / "output")
            self.assertEqual(len(report["records"]), 2)
            self.assertEqual(report["candidate_f_number"], 0.8)
            for row in report["records"]:
                self.assertEqual(row["reference_type"], "embedded UFF")
                self.assertEqual(set(row["batch_parity"]), {"1.7", "0.8"})
                self.assertTrue(all(item["passed"] for item in row["batch_parity"].values()))
            self.assertEqual(report, json.loads((root / "output/metrics.json").read_text("utf-8")))


class BatchProfileReportTests(unittest.TestCase):
    def test_profile_compares_each_batch_to_its_own_f_number(self):
        def fake_subprocess(command, **kwargs):
            f_number = float(command[command.index("--f-number") + 1])
            batch = (int(command[command.index("--angle-batch-size") + 1])
                     if "--angle-batch-size" in command else None)
            path = command[command.index("--result-path") + 1]
            # Different apertures intentionally have different outputs.
            np.savez(path, rf=np.ones((2, 2), complex) * f_number,
                     bmode=np.ones((2, 2)) * f_number)
            row = {"f_number": f_number, "angle_batch_size": batch, "median_seconds": 1,
                   "minimum_seconds": 0.9, "maximum_seconds": 1.1, "median_fps": 1,
                   "rss_baseline_mib": 100, "rss_sampled_peak_mib": 120}
            return SimpleNamespace(stdout=json.dumps(row))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.uff"
            source.write_bytes(b"synthetic test")
            with patch("ultrasound_bmode.batch_profile_cli.subprocess.run",
                       side_effect=fake_subprocess) as runner:
                report = run_batch_profile(source, root / "report")
            self.assertEqual(runner.call_count, 6)
            self.assertEqual(len(report["records"]), 6)
            for row in report["records"]:
                if row["angle_batch_size"] is not None:
                    self.assertTrue(row["parity_to_same_f_number_unbatched"]["passed"])
            self.assertTrue((root / "report/batch_profile.png").is_file())


if __name__ == "__main__":
    unittest.main()
