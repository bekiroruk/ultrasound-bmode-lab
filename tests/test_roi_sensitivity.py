import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.real_data import PlaneWaveResult, select_transmit_indices
from ultrasound_bmode.roi import LumenRoi
from ultrasound_bmode.roi_sensitivity_cli import (
    run_roi_sensitivity,
    sensitivity_conditions,
    summarize,
)


class RoiSensitivityTests(unittest.TestCase):
    def test_conditions_are_one_factor_at_a_time(self):
        roi = LumenRoi(1e-3, 20e-3, 2.2e-3)
        conditions = sensitivity_conditions(roi)
        self.assertEqual(len(conditions), 10)
        self.assertEqual(len({row[0] for row in conditions}), 10)
        self.assertEqual(conditions[0], ("baseline", roi, (0, 0)))
        for _, changed, origin in conditions[1:7]:
            count = sum(a != b for a, b in zip(
                (roi.center_x_m, roi.center_z_m, roi.radius_m),
                (changed.center_x_m, changed.center_z_m, changed.radius_m), strict=True))
            self.assertEqual(count, 1)
            self.assertEqual(origin, (0, 0))
        self.assertTrue(all(row[1] == roi for row in conditions[7:]))
        self.assertEqual([row[2] for row in conditions[7:]], [(0, 4), (4, 0), (4, 4)])

    def test_summary_keeps_roi_ranges_separate_from_origin_intervals(self):
        records = []
        for condition, estimate, interval in (
            ("baseline", 0.01, [-0.02, 0.03]), ("x_minus", -0.01, [-0.03, 0.04]),
            ("origin_4_4", 0.01, [0.001, 0.02]),
        ):
            records.append({
                "case": "fixture", "condition": condition,
                "bootstrap": {"paired_differences": [{
                    "first": "cubic", "second": "linear",
                    "metrics": {"generalized_cnr": {
                        "estimate": estimate, "percentile95": interval}}} ]}})
        row = summarize(records)[0]
        self.assertEqual(row["roi_delta_gcnr_min_max"], [-0.01, 0.01])
        self.assertTrue(row["roi_point_sign_changes"])
        self.assertEqual(row["origin_interval_lower_min_max"], [-0.02, 0.001])
        self.assertEqual(row["origin_intervals_containing_zero"], 1)
        self.assertEqual(row["origin_count"], 2)

    def test_missing_sources_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                run_roi_sensitivity(root, root / "out", samples=20)
            self.assertFalse((root / "out").exists())
            with self.assertRaises(ValueError):
                run_roi_sensitivity(root, root / "out", samples=True)

    def test_two_acquisitions_report_masks_provenance_and_all_conditions(self):
        from ultrasound_bmode.external_validation_cli import _cases
        from ultrasound_bmode.interpolation_transfer_cli import SETTINGS_FILES

        x = np.linspace(-15e-3, 15e-3, 161)
        z = np.linspace(5e-3, 40e-3, 161)
        envelope = 1 + np.arange(x.size)[None, :] / x.size + np.zeros((z.size, 1))
        sources = {
            key: SimpleNamespace(x_axis_m=x, z_axis_m=z,
                                 reference_iq=envelope if key == "picmus_cross" else None,
                                 transmit_angles_rad=np.linspace(-0.1, 0.1, count))
            for key, count in (("picmus_cross", 75), ("epfl_v5", 87))
        }
        calls = []

        def reconstruct(source, **kwargs):
            self.assertTrue(kwargs["analytic"])
            self.assertEqual(kwargs["f_number"], 1.7)
            self.assertIsNotNone(kwargs["analytic_cache"])
            stride = 2 if source.reference_iq is not None else 1
            self.assertEqual(kwargs["lateral_stride"], stride)
            calls.append(kwargs)
            signal = envelope[::stride, ::stride].astype(complex)
            return PlaneWaveResult(
                signal, np.zeros(signal.shape), x[::stride], z[::stride],
                select_transmit_indices(source.transmit_angles_rad, kwargs["angle_count"]))

        prefix = "ultrasound_bmode.roi_sensitivity_cli."
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for case in _cases(root):
                if case.identifier in sources:
                    case.path.parent.mkdir(parents=True, exist_ok=True)
                    case.path.write_bytes(b"fixture")
            settings = root / "epfl/settings"
            settings.mkdir()
            for name in SETTINGS_FILES:
                (settings / name).write_bytes(b"settings fixture")
            with patch(prefix + "_load", side_effect=lambda case, _: sources[case.identifier]), \
                 patch(prefix + "_provenance", side_effect=lambda *_: {"sha256": "fixture"}), \
                 patch(prefix + "reference_bmode", return_value=np.zeros(envelope.shape)), \
                 patch(prefix + "locate_carotid_lumen",
                       return_value=LumenRoi(0, 20e-3, 2.2e-3)) as locate, \
                 patch(prefix + "prepare_analytic_channel_cache", return_value=object()), \
                 patch(prefix + "numba_plane_wave_delay_and_sum", side_effect=reconstruct), \
                 patch(prefix + "_plot") as plot:
                report = run_roi_sensitivity(root, root / "out", samples=20)
            self.assertEqual(len(calls), 8)
            self.assertEqual(locate.call_count, 1)
            self.assertEqual(plot.call_count, 2)
            self.assertEqual(len(report["records"]), 20)
            self.assertEqual(len(report["summaries"]), 4)
            self.assertEqual(report["datasets"][0]["case"], "picmus_cross")
            self.assertEqual(report["datasets"][1]["case"], "epfl_v5")
            self.assertEqual(report["datasets"][1]["roi_m"]["center_x_m"], 6e-3)
            self.assertIn("settings_sha256", report["datasets"][1])
            self.assertFalse(report["datasets"][1]["independent_reference_available"])
            for row in report["records"]:
                for pair in row["bootstrap"]["paired_differences"]:
                    self.assertEqual(pair["metrics"]["generalized_cnr"]["percentile95"], [0, 0])
            self.assertEqual(report, json.loads((root / "out/metrics.json").read_text("utf-8")))


if __name__ == "__main__":
    unittest.main()
