import tempfile
import unittest
from pathlib import Path

import numpy as np

from ultrasound_bmode.epfl import load_epfl_acquisition

EPFL_SAMPLE = Path("data/raw/epfl/invivo_14965.npz")
EPFL_SETTINGS = Path("data/raw/epfl/settings")


class EpflLoaderTests(unittest.TestCase):
    def test_loader_builds_geometry_from_published_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = root / "settings"
            settings.mkdir()
            (settings / "beamforming_settings.yaml").write_text(
                """transducer:
  c0: 1540.0
  n_elements: 4
  pitch: 0.00023
acquisition:
  sampling_frequency: 20000000.0
""",
                encoding="utf-8",
            )
            np.save(settings / "steering_angles.npy", np.array([-0.1, 0.0, 0.1]))
            np.save(settings / "time_axis.npy", np.arange(8) / 20e6 - 1e-6)
            data = np.zeros((1, 3, 4, 8), dtype=np.float32)
            np.savez(
                root / "sample.npz",
                data=data,
                body_region=np.array("carotid"),
                volunteer_id=np.array("005"),
            )

            acquisition = load_epfl_acquisition(
                root / "sample.npz", settings, lateral_pixels=5, axial_pixels=6
            )

            self.assertEqual(acquisition.channel_data.shape, (3, 4, 8))
            self.assertEqual(acquisition.x_axis_m.size, 5)
            self.assertEqual(acquisition.z_axis_m.size, 6)
            self.assertIsNone(acquisition.reference_iq)
            self.assertIn("volunteer 005", acquisition.name)
            self.assertAlmostEqual(acquisition.sampling_frequency_hz, 20e6)

    def test_loader_rejects_dimension_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = root / "settings"
            settings.mkdir()
            (settings / "beamforming_settings.yaml").write_text(
                "c0: 1540\nn_elements: 4\npitch: 0.00023\nsampling_frequency: 20000000\n",
                encoding="utf-8",
            )
            np.save(settings / "steering_angles.npy", np.array([-0.1, 0.0, 0.1]))
            np.save(settings / "time_axis.npy", np.arange(8) / 20e6)
            np.savez(
                root / "bad.npz",
                data=np.zeros((1, 2, 4, 8), dtype=np.float32),
                body_region=np.array("carotid"),
                volunteer_id=np.array("005"),
            )
            with self.assertRaises(ValueError):
                load_epfl_acquisition(root / "bad.npz", settings)


@unittest.skipUnless(EPFL_SAMPLE.is_file(), "EPFL RF sample not installed")
class InstalledEpflTests(unittest.TestCase):
    def test_public_sample_dimensions(self):
        acquisition = load_epfl_acquisition(EPFL_SAMPLE, EPFL_SETTINGS)
        self.assertEqual(acquisition.channel_data.shape, (87, 192, 2133))
        self.assertEqual(acquisition.transmit_angles_rad.size, 87)
        self.assertAlmostEqual(acquisition.sampling_frequency_hz, 20_833_333.333333332)
        self.assertIn("volunteer 005", acquisition.name)


if __name__ == "__main__":
    unittest.main()
