import copy
import unittest
from unittest.mock import Mock, patch

import numpy as np

from ultrasound_bmode.aperture_study_cli import select_candidate
from ultrasound_bmode.runtime_profile_cli import profile_call


def row(f_number=1.7, lateral=0.65, axial=0.58, gcnr=0.92):
    return {
        "angle_count": 11, "stride": 2, "f_number": f_number,
        "resolution": {"median_lateral_fwhm_mm": lateral, "median_axial_fwhm_mm": axial,
                       "valid_axial_targets": 7, "valid_lateral_targets": 7},
        "contrast": {"cysts": {name: {"generalized_cnr": gcnr}
                               for name in ("shallow_cyst", "deep_cyst")}},
    }


class ApertureSelectionTests(unittest.TestCase):
    def test_selects_narrowest_candidate_meeting_both_guardrails(self):
        self.assertEqual(select_candidate([row(), row(0.8, 0.57), row(1.0, 0.60)]), 0.8)

    def test_rejects_loss_in_either_cyst_and_excessive_axial_width(self):
        for cyst in ("shallow_cyst", "deep_cyst"):
            candidate = row(0.8, 0.57)
            candidate["contrast"]["cysts"][cyst]["generalized_cnr"] = 0.88
            self.assertEqual(select_candidate([row(), candidate]), 1.7)
        self.assertEqual(select_candidate([row(), row(0.8, 0.57, axial=0.70)]), 1.7)

    def test_rejects_missing_widths_and_nonfinite_contrast(self):
        for invalid in (None, np.nan, np.inf):
            candidate = row(0.8, 0.57)
            candidate["contrast"]["cysts"]["deep_cyst"]["generalized_cnr"] = invalid
            self.assertEqual(select_candidate([row(), candidate]), 1.7)
        candidate = row(0.8, 0.57)
        candidate["resolution"]["valid_lateral_targets"] = 6
        self.assertEqual(select_candidate([row(), candidate]), 1.7)

    def test_selection_does_not_use_75_angle_or_fine_grid_results(self):
        candidate = row(0.8, 0.30)
        candidate["angle_count"] = 75
        fine = copy.deepcopy(candidate)
        fine.update(angle_count=11, stride=1)
        self.assertEqual(select_candidate([row(), candidate, fine]), 1.7)

    def test_missing_or_invalid_baseline_fails_clearly(self):
        for rows in ([], [row(0.8)], [row(axial=np.nan)]):
            with self.assertRaisesRegex(ValueError, "baseline"):
                select_candidate(rows)


class RuntimeProtocolTests(unittest.TestCase):
    def test_separates_warmup_timed_calls_and_memory_pass(self):
        function = Mock(return_value="result")
        with patch("ultrasound_bmode.runtime_profile_cli.time.perf_counter",
                   side_effect=[0, 0.5, 1, 1.2, 2, 2.4]):
            report, result = profile_call(function, repeats=2)
        self.assertEqual(function.call_count, 4)
        self.assertEqual(result, "result")
        self.assertAlmostEqual(report["warmup_full_call_seconds_excluded"], 0.5)
        self.assertAlmostEqual(report["median_seconds"], 0.3)
        self.assertGreaterEqual(report["rss_sampled_peak_mib"], report["rss_baseline_mib"])
        self.assertGreaterEqual(report["rss_sample_count"], 2)

    def test_invalid_repeats_or_sampling_period_rejected(self):
        for kwargs in ({"repeats": 1}, {"sample_interval_s": 0}):
            with self.assertRaises(ValueError):
                profile_call(lambda: None, **kwargs)


if __name__ == "__main__":
    unittest.main()
