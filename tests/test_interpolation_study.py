import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.interpolation_study_cli import run_interpolation_study
from ultrasound_bmode.real_data import PlaneWaveResult, UFFAcquisition


class InterpolationStudyReportTests(unittest.TestCase):
    def test_report_retains_both_methods_speeds_and_no_selection_claim(self):
        acquisition = UFFAcquisition(
            channel_data=np.zeros((13, 2, 8), dtype=np.float32),
            sampling_frequency_hz=20e6,
            sound_speed_m_s=1540.0,
            initial_time_s=0.0,
            element_x_m=np.array([-0.5e-3, 0.5e-3]),
            transmit_angles_rad=np.linspace(-0.2, 0.2, 13),
            x_axis_m=np.linspace(-15e-3, 15e-3, 5),
            z_axis_m=np.linspace(5e-3, 55e-3, 7),
            reference_iq=(np.arange(35, dtype=float).reshape(7, 5) + 1).astype(complex),
            name="Synthetic report fixture",
            citation="Not measured data",
        )

        def fake_reconstruct(adjusted, angle_count, interpolation, **kwargs):
            x, z = adjusted.x_axis_m[::2], adjusted.z_axis_m[::2]
            value = 1.0 if interpolation == "linear" else 1.1
            rf = np.full((z.size, x.size), value + 0j)
            return PlaneWaveResult(
                rf=rf, bmode_db=np.arange(rf.size, dtype=float).reshape(rf.shape),
                x_axis_m=x, z_axis_m=z,
                angle_indices=np.arange(angle_count),
            )

        def fake_measure(kind, envelope, x, z):
            if kind == "contrast":
                return {"cysts": {
                    "shallow_cyst": {"generalized_cnr": 0.8},
                    "deep_cyst": {"generalized_cnr": 0.7},
                }}
            point = {"detected_x_mm": 0.0, "detected_z_mm": 10.0}
            return {
                "median_lateral_fwhm_mm": 0.6,
                "median_axial_fwhm_mm": 0.5,
                "position_rmse_mm": 0.2,
                "points": [point],
            }

        def fake_panels(panels, x, z, output, *args):
            Path(output).write_bytes(b"test plot")

        def fake_plot(records, output):
            Path(output).write_bytes(b"test plot")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("contrast_speckle", "resolution_distortion"):
                (root / f"PICMUS_experiment_{name}.uff").write_bytes(b"test source")
            with patch("ultrasound_bmode.interpolation_study_cli.load_picmus_uff",
                       return_value=acquisition), \
                 patch("ultrasound_bmode.interpolation_study_cli.prepare_analytic_channel_cache",
                       return_value=SimpleNamespace(size_mib=1.0, preparation_seconds=0.01)), \
                 patch("ultrasound_bmode.interpolation_study_cli.numba_plane_wave_delay_and_sum",
                       side_effect=fake_reconstruct), \
                 patch("ultrasound_bmode.interpolation_study_cli._measure",
                       side_effect=fake_measure), \
                 patch("ultrasound_bmode.interpolation_study_cli._save_panels",
                       side_effect=fake_panels), \
                 patch("ultrasound_bmode.interpolation_study_cli._plot_sound_speed",
                       side_effect=fake_plot):
                report = run_interpolation_study(root, root / "report")

            self.assertEqual(len(report["interpolation_records"]), 8)
            self.assertEqual(len(report["sound_speed_records"]), 10)
            self.assertEqual(
                {row["interpolation"] for row in report["interpolation_records"]},
                {"linear", "cubic"},
            )
            self.assertEqual(
                {row["sound_speed_m_s"] for row in report["sound_speed_records"]},
                {1460.0, 1500.0, 1540.0, 1580.0, 1620.0},
            )
            self.assertIn("defaults remain unchanged", report["reference_limit"])
            self.assertEqual(report, json.loads(
                (root / "report/metrics.json").read_text(encoding="utf-8")
            ))


if __name__ == "__main__":
    unittest.main()
