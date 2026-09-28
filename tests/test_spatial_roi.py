import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.analytic_roi_cli import _save_report
from ultrasound_bmode.metrics import evaluate_cyst
from ultrasound_bmode.roi import LumenRoi
from ultrasound_bmode.spatial_roi import paired_spatial_bootstrap


def fixture():
    x = np.arange(64) * 0.25e-3 - 8e-3
    z = np.arange(64) * 0.25e-3 + 12e-3
    roi = LumenRoi(0.0, 20e-3, 2e-3)
    rng = np.random.default_rng(41)
    image = np.repeat(np.repeat(rng.uniform(0.2, 1.8, (16, 16)), 4, axis=0), 4, axis=1)
    xx, zz = np.meshgrid(x, z)
    image[xx**2 + (zz - roi.center_z_m)**2 <= roi.radius_m**2] *= 0.4
    return image, x, z, roi


class SpatialRoiTests(unittest.TestCase):
    def test_determinism_and_paired_identity(self):
        image, x, z, roi = fixture()
        kwargs = {"block_size": 4, "samples": 40, "seed": 3, "comparisons": (("a", "b"),)}
        first = paired_spatial_bootstrap({"a": image, "b": image.copy()}, x, z, roi, **kwargs)
        second = paired_spatial_bootstrap({"a": image, "b": image.copy()}, x, z, roi, **kwargs)
        self.assertEqual(first, second)
        for metric in first["paired_differences"][0]["metrics"].values():
            self.assertEqual(metric, {"estimate": 0.0, "percentile95": [0.0, 0.0]})

    def test_point_estimates_match_existing_metric_and_do_not_depend_on_block_size(self):
        image, x, z, roi = fixture()
        expected = evaluate_cyst(image, x, z, center_x_m=roi.center_x_m,
                                center_z_m=roi.center_z_m, target_radius_m=roi.radius_m,
                                background_inner_radius_m=roi.radius_m + 1e-3,
                                background_outer_radius_m=roi.radius_m + 3e-3)
        for size in (1, 4, 8):
            result = paired_spatial_bootstrap({"a": image}, x, z, roi,
                                            block_size=size, samples=20)
            for name, metric in result["images"]["a"].items():
                self.assertAlmostEqual(metric["estimate"], getattr(expected, name))
            self.assertEqual(sum((result["target_pixels"], result["background_pixels"])),
                             np.sum((x[None, :]**2 + (z[:, None] - roi.center_z_m)**2
                                     <= (roi.radius_m + 3e-3)**2)
                                    & ~((x[None, :]**2 + (z[:, None] - roi.center_z_m)**2
                                         > roi.radius_m**2)
                                        & (x[None, :]**2 + (z[:, None] - roi.center_z_m)**2
                                           <= (roi.radius_m + 1e-3)**2))))

    def test_blocks_widen_contrast_interval_on_tile_correlated_fixture(self):
        image, x, z, roi = fixture()
        widths = []
        for size in (1, 4):
            result = paired_spatial_bootstrap({"a": image}, x, z, roi,
                                            block_size=size, samples=200, seed=5)
            low, high = result["images"]["a"]["contrast_db"]["percentile95"]
            widths.append(high - low)
        self.assertGreater(widths[1], 1.5 * widths[0])

    def test_tile_draws_preserve_all_pixels_within_each_selected_tile(self):
        image, x, z, roi = fixture()
        # Capture one image's point and replicate inputs, and verify intensities
        # in a tile-correlated field are repeated as groups rather than singly.
        from ultrasound_bmode.spatial_roi import _statistics
        with patch("ultrasound_bmode.spatial_roi._statistics", wraps=_statistics) as stats:
            result = paired_spatial_bootstrap({"a": image}, x, z, roi,
                                            block_size=4, samples=20)
        target_original, background_original = stats.call_args_list[0].args
        for target, background in [call.args for call in stats.call_args_list[1:]]:
            for original, sampled in ((target_original, target), (background_original, background)):
                values, counts = np.unique(original, return_counts=True)
                for value, count in zip(values, counts, strict=True):
                    self.assertEqual(np.count_nonzero(sampled == value) % count, 0)
        self.assertEqual(len(stats.call_args_list), result["samples"] + 1)

    def test_invalid_inputs_and_insufficient_support_are_rejected(self):
        image, x, z, roi = fixture()
        for kwargs in ({"samples": 1}, {"block_size": True}, {"block_size": 64},
                       {"seed": -1}, {"comparisons": (("a", "missing"),)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                paired_spatial_bootstrap({"a": image}, x, z, roi, **kwargs)
        for bad in (image[:-1], image * np.nan, -image, image.astype(complex)):
            with self.assertRaises(ValueError):
                paired_spatial_bootstrap({"a": bad}, x, z, roi)
        with self.assertRaisesRegex(ValueError, "annulus"):
            paired_spatial_bootstrap({"a": image}, x, z, LumenRoi(x[0], 20e-3, 2e-3))
        with self.assertRaisesRegex(ValueError, "axes"):
            paired_spatial_bootstrap({"a": image}, x[::-1], z, roi)
        irregular = x.copy()
        irregular[10] += 0.1e-3
        with self.assertRaisesRegex(ValueError, "axes"):
            paired_spatial_bootstrap({"a": image}, irregular, z, roi)

    def test_float32_quantized_grid_is_accepted(self):
        image, x, z, roi = fixture()
        result = paired_spatial_bootstrap(
            {"a": image}, x.astype(np.float32).astype(float),
            z.astype(np.float32).astype(float), roi, samples=20)
        self.assertEqual(result["samples"], 20)

    def test_shifted_origins_preserve_points_pixels_and_paired_identity(self):
        image, x, z, roi = fixture()
        baseline = paired_spatial_bootstrap({"a": image, "b": image}, x, z, roi,
                                           block_size=8, samples=20,
                                           comparisons=(("a", "b"),))
        for origin in ((0, 0), (0, 4), (4, 0), (4, 4)):
            actual = paired_spatial_bootstrap({"a": image, "b": image}, x, z, roi,
                                             block_size=8, block_origin=origin, samples=20,
                                             comparisons=(("a", "b"),))
            if origin == (0, 0):
                self.assertEqual(actual, baseline)
            self.assertEqual(actual["target_pixels"], baseline["target_pixels"])
            self.assertEqual(actual["background_pixels"], baseline["background_pixels"])
            self.assertEqual(actual["grid_anchor_pixels"], list(origin))
            for name, metric in actual["images"]["a"].items():
                self.assertEqual(metric["estimate"], baseline["images"]["a"][name]["estimate"])
                self.assertEqual(
                    actual["paired_differences"][0]["metrics"][name]["percentile95"], [0, 0])

    def test_invalid_origins_fail(self):
        image, x, z, roi = fixture()
        for origin in ((-1, 0), (8, 0), (0,), (True, 0), (0.5, 0), None):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                paired_spatial_bootstrap({"a": image}, x, z, roi,
                                         block_size=8, block_origin=origin, samples=20)

    def test_report_roundtrip_retains_all_block_sizes_and_paired_differences(self):
        image, x, z, roi = fixture()
        studies = [paired_spatial_bootstrap({"a": image, "b": image}, x, z, roi,
                                          block_size=size, samples=20,
                                          comparisons=(("a", "b"),))
                   for size in (1, 2, 4, 8)]
        report = {"scope": "Synthetic report fixture only", "spatial_bootstrap": studies}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _save_report(report, root)
            self.assertEqual(report, json.loads((root / "metrics.json").read_text("utf-8")))
            self.assertIn("not diagnostic improvement", (root / "README.md").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
