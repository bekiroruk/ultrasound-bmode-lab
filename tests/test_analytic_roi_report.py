import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.analytic_roi_cli import run_analytic_roi
from ultrasound_bmode.real_data import PlaneWaveResult, select_transmit_indices
from ultrasound_bmode.roi import LumenRoi


class AnalyticRoiReportTests(unittest.TestCase):
    def test_frozen_grid_modes_cache_and_report(self):
        x = np.linspace(-10e-3, 10e-3, 257)
        z = np.linspace(10e-3, 30e-3, 257)
        xx, zz = np.meshgrid(x, z)
        envelope = np.ones(xx.shape)
        envelope[xx**2 + (zz - 20e-3)**2 <= (2.2e-3)**2] = 0.2
        acquisition = SimpleNamespace(
            x_axis_m=x, z_axis_m=z, reference_iq=envelope.astype(complex),
            transmit_angles_rad=np.linspace(-0.1, 0.1, 75),
        )
        cache = object()
        calls = []

        def reconstruct(source, **kwargs):
            self.assertIs(source, acquisition)
            self.assertEqual(kwargs["f_number"], 1.7)
            self.assertEqual(kwargs["angle_batch_size"], 8)
            self.assertIs(kwargs["analytic_cache"], cache if kwargs["analytic"] else None)
            calls.append((kwargs["analytic"], kwargs["interpolation"], kwargs["angle_count"]))
            signal = envelope[::2, ::2] * (1 + 0j if kwargs["analytic"] else 1)
            return PlaneWaveResult(
                signal, 20 * np.log10(np.abs(signal)), x[::2], z[::2],
                select_transmit_indices(acquisition.transmit_angles_rad, kwargs["angle_count"]),
            )

        prefix = "ultrasound_bmode.analytic_roi_cli."
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(prefix + "load_picmus_uff", return_value=acquisition), \
                 patch(prefix + "reference_bmode", return_value=20 * np.log10(envelope)), \
                 patch(prefix + "locate_carotid_lumen",
                       return_value=LumenRoi(0, 20e-3, 2.2e-3)) as locate, \
                 patch(prefix + "_provenance", return_value={"sha256": "fixture"}), \
                 patch(prefix + "prepare_analytic_channel_cache", return_value=cache), \
                 patch(prefix + "numba_plane_wave_delay_and_sum", side_effect=reconstruct):
                report = run_analytic_roi(Path("fixture.uff"), root, samples=20)
            self.assertEqual(locate.call_count, 1)
            self.assertEqual(len(calls), 6)
            self.assertEqual(len(report["spatial_bootstrap"]), 4)
            self.assertEqual(report["datasets"][0]["sha256"], "fixture")
            self.assertTrue((root / "analytic_roi.png").is_file())
            self.assertTrue((root / "metrics.json").is_file())
            for row in report["spatial_bootstrap"]:
                self.assertEqual(len(row["images"]), 7)
                self.assertEqual(len(row["paired_differences"]), 4)
                for comparison in row["paired_differences"][1::2]:
                    for metric in comparison["metrics"].values():
                        self.assertEqual(metric["percentile95"], [0.0, 0.0])

    def test_missing_reference_and_invalid_protocol_fail_before_output(self):
        prefix = "ultrasound_bmode.analytic_roi_cli."
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "out"
            with patch(prefix + "load_picmus_uff",
                       return_value=SimpleNamespace(reference_iq=None)), \
                 self.assertRaisesRegex(ValueError, "reference"):
                run_analytic_roi(Path("fixture.uff"), root, samples=20)
            with self.assertRaisesRegex(ValueError, "samples"):
                run_analytic_roi(Path("missing.uff"), root, samples=0)
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
