import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ultrasound_bmode.accelerated import numba_available, numba_plane_wave_delay_and_sum
from ultrasound_bmode.external_validation_cli import ValidationCase
from ultrasound_bmode.interpolation_transfer_cli import (
    SETTINGS_FILES,
    _validate_geometry,
    run_interpolation_transfer,
)
from ultrasound_bmode.metrics import evaluate_similarity
from ultrasound_bmode.real_data import (
    PlaneWaveResult,
    UFFAcquisition,
    reference_bmode,
    select_transmit_indices,
)


def acquisition_fixture(reference=True):
    rng = np.random.default_rng(109)
    return UFFAcquisition(
        channel_data=rng.normal(size=(13, 3, 768)).astype(np.float32),
        sampling_frequency_hz=20e6, sound_speed_m_s=1510, initial_time_s=0,
        element_x_m=np.linspace(-1e-3, 1e-3, 3),
        transmit_angles_rad=np.linspace(-0.2, 0.2, 13),
        x_axis_m=np.linspace(-2e-3, 2e-3, 9), z_axis_m=np.linspace(5e-3, 25e-3, 17),
        reference_iq=(rng.normal(size=(17, 9)) + 1j * rng.normal(size=(17, 9))
                      if reference else None),
        name="Synthetic interpolation transfer fixture", citation="Not measured data",
    )


class InterpolationTransferTests(unittest.TestCase):
    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_frozen_protocol_real_cache_parity_reference_semantics_and_json(self):
        embedded = acquisition_fixture()
        external = acquisition_fixture(reference=False)
        observed = []

        def reconstruct(acquisition, **kwargs):
            result = numba_plane_wave_delay_and_sum(acquisition, **kwargs)
            observed.append((acquisition, kwargs, result))
            return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / "fixture.uff", root / "external.npz"]
            for path in paths:
                path.write_bytes(b"synthetic source")
            settings = root / "epfl/settings"
            settings.mkdir(parents=True)
            for name in SETTINGS_FILES:
                (settings / name).write_bytes(b"synthetic settings")
            cases = (
                ValidationCase("picmus_cross", "Synthetic embedded", paths[0], "uff",
                               "Test", "Test", "Test", "Test"),
                ValidationCase("epfl_v5", "Synthetic external", paths[1], "epfl",
                               "Test", "Test", "Test", "Test"),
            )
            with patch("ultrasound_bmode.interpolation_transfer_cli._cases", return_value=cases), \
                 patch("ultrasound_bmode.interpolation_transfer_cli._load",
                       side_effect=(embedded, external)), \
                 patch("ultrasound_bmode.interpolation_transfer_cli.numba_plane_wave_delay_and_sum",
                       side_effect=reconstruct):
                report = run_interpolation_transfer(root, root / "report")
            self.assertEqual(report, json.loads((root / "report/metrics.json").read_text("utf-8")))
            self.assertEqual(len(report["records"]), 4)
            self.assertEqual(len(observed), 12)
            self.assertIn("not a quality score", report["reference_policy"])
            self.assertIn("No parameter", report["scope"])
            self.assertEqual(report["datasets"][0]["sha256"],
                             hashlib.sha256(b"synthetic source").hexdigest())
            self.assertEqual(report["datasets"][1]["settings_sha256"], {
                name: hashlib.sha256(b"synthetic settings").hexdigest() for name in SETTINGS_FILES
            })
            for source, kwargs, _ in observed:
                self.assertEqual(kwargs["f_number"], 1.7)
                self.assertTrue(kwargs["analytic"])
                self.assertEqual(kwargs["dynamic_range_db"], 60)
                self.assertEqual(source.sound_speed_m_s, 1510)
                self.assertEqual(kwargs["axial_stride"], 2 if source is embedded else 1)
                self.assertEqual(kwargs["lateral_stride"], kwargs["axial_stride"])
                if "analytic_cache" in kwargs:
                    self.assertEqual(kwargs["angle_batch_size"], 8)
                    self.assertIs(kwargs["analytic_cache"].source_channel_data, source.channel_data)
                    self.assertEqual(kwargs["analytic_cache"].preparation_batch_size, 8)
                else:
                    self.assertEqual(kwargs["interpolation"], "cubic")
                    self.assertNotIn("angle_batch_size", kwargs)
            for row in report["records"]:
                self.assertTrue(row["cubic_cache_batch_parity"]["passed"])
                self.assertLessEqual(row["cubic_cache_batch_parity"]["rf_max_absolute_error"], 1e-7)
                self.assertEqual(row["sound_speed_m_s"], 1510)
                self.assertEqual(row["angle_count"], len(row["angle_indices"]))
                self.assertEqual(row["acquired_angle_count"], 13)
                if row["case"] == "picmus_cross":
                    self.assertEqual(row["reference_type"], "embedded UFF")
                    self.assertEqual(row["output_shape"], [9, 5])
                    self.assertEqual(row["x_axis_m"], embedded.x_axis_m[::2].tolist())
                    self.assertEqual(row["z_axis_m"], embedded.z_axis_m[::2].tolist())
                    for mode in ("linear", "cubic"):
                        result = next(result for source, kwargs, result in observed
                                      if source is embedded and "analytic_cache" in kwargs
                                      and kwargs["angle_count"] == row["angle_count"]
                                      and kwargs["interpolation"] == mode)
                        expected = evaluate_similarity(
                            reference_bmode(embedded)[::2, ::2], result.bmode_db
                        ).to_dict()
                        self.assertEqual(row["embedded_reference_similarity"][mode], expected)
                else:
                    self.assertEqual(row["reference_type"], "unavailable")
                    self.assertIsNone(row["embedded_reference_similarity"])
                    self.assertEqual(row["output_shape"], [17, 9])
                self.assertIn("ssim", row["interpolation_change_not_quality"])
                self.assertGreater((root / "report" / f"{row['case']}.png").stat().st_size, 1000)
            markdown = (root / "report/README.md").read_text("utf-8")
            self.assertIn("Unavailable", markdown)
            self.assertIn("not quality", markdown)

    def test_geometry_rejects_shifted_axes_angle_order_and_broadcastable_images(self):
        acquisition = acquisition_fixture()
        x, z = acquisition.x_axis_m[::2], acquisition.z_axis_m[::2]
        result = PlaneWaveResult(
            rf=np.ones((len(z), len(x)), complex), bmode_db=np.zeros((len(z), len(x))),
            x_axis_m=x, z_axis_m=z,
            angle_indices=select_transmit_indices(acquisition.transmit_angles_rad, 11),
        )
        _validate_geometry(acquisition, result, 2, 11)
        for changed in (
            replace(result, x_axis_m=x + 1e-3), replace(result, z_axis_m=z + 1e-3),
            replace(result, angle_indices=result.angle_indices[::-1]),
            replace(result, rf=result.rf[:1]), replace(result, bmode_db=result.bmode_db[:1]),
        ):
            with self.subTest(result=changed), self.assertRaises(AssertionError):
                _validate_geometry(acquisition, changed, 2, 11)

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_cache_parity_failure_prevents_success_report(self):
        acquisition = acquisition_fixture()

        def altered_reconstruction(source, **kwargs):
            result = numba_plane_wave_delay_and_sum(source, **kwargs)
            if kwargs["interpolation"] == "cubic" and "analytic_cache" in kwargs:
                return replace(result, rf=result.rf + 0.1)
            return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.uff"
            path.write_bytes(b"synthetic source")
            case = ValidationCase("picmus_cross", "Synthetic", path, "uff", "T", "T", "T", "T")
            with patch("ultrasound_bmode.interpolation_transfer_cli._cases", return_value=(case,)), \
                 patch("ultrasound_bmode.interpolation_transfer_cli._load", return_value=acquisition), \
                 patch("ultrasound_bmode.interpolation_transfer_cli.numba_plane_wave_delay_and_sum",
                       side_effect=altered_reconstruction), \
                 self.assertRaises(AssertionError):
                run_interpolation_transfer(root, root / "report")
            self.assertFalse((root / "report/metrics.json").exists())

    def test_missing_settings_fail_before_loading_or_creating_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.npz"
            path.write_bytes(b"synthetic source")
            case = ValidationCase("epfl_v5", "Synthetic", path, "epfl", "T", "T", "T", "T")
            with patch("ultrasound_bmode.interpolation_transfer_cli._cases", return_value=(case,)), \
                 patch("ultrasound_bmode.interpolation_transfer_cli._load") as loader, \
                 self.assertRaisesRegex(FileNotFoundError, "beamforming_settings.yaml"):
                run_interpolation_transfer(root, root / "report")
            loader.assert_not_called()
            self.assertFalse((root / "report").exists())


if __name__ == "__main__":
    unittest.main()
