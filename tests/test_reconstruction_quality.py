"""Small, offline end-to-end checks for the comparison report."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.real_data import UFFAcquisition
from ultrasound_bmode.reconstruction_quality_cli import run_quality_comparison


class QualityReportTests(unittest.TestCase):
    def test_numpy_report_writes_metrics_provenance_and_figure(self):
        rng = np.random.default_rng(19)
        acquisition = UFFAcquisition(
            channel_data=rng.normal(size=(1, 3, 1024)),
            sampling_frequency_hz=20e6, sound_speed_m_s=1540.0, initial_time_s=0.0,
            element_x_m=np.array([-1e-3, 0.0, 1e-3]),
            transmit_angles_rad=np.array([0.0]),
            x_axis_m=np.linspace(-1e-3, 1e-3, 8),
            z_axis_m=np.linspace(5e-3, 30e-3, 12),
            reference_iq=rng.normal(size=(12, 8)) + 1j * rng.normal(size=(12, 8)),
            name="Synthetic report fixture", citation="Test data, not a clinical acquisition",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.uff"
            path.write_bytes(b"synthetic placeholder for checksum test")
            with patch(
                "ultrasound_bmode.reconstruction_quality_cli.load_picmus_uff",
                return_value=acquisition,
            ):
                report = run_quality_comparison([path], root / "report", [1], backend="numpy")
            stored = json.loads((root / "report/quality_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(report, stored)
            self.assertEqual(len(stored["results"]), 1)
            row = stored["results"][0]
            self.assertEqual(row["output_shape"], [6, 4])
            self.assertEqual(len(row["sha256"]), 64)
            self.assertTrue((root / "report" / row["figure"]).is_file())
            self.assertIn("SSIM before", (root / "report/README.md").read_text(encoding="utf-8"))

    def test_invalid_settings_fail_before_data_access(self):
        for kwargs in ({"stride": 0}, {"f_number": float("nan")}, {"backend": "cuda"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_quality_comparison([Path("missing.uff")], Path("unused"), [1], **kwargs)


if __name__ == "__main__":
    unittest.main()
