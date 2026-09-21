import importlib.util
import unittest
from pathlib import Path

import numpy as np

from ultrasound_bmode.real_data import _select_angles, beamform_plane_wave

DATASET = Path("data/raw/PICMUS_carotid_cross.uff")
HAS_H5PY = importlib.util.find_spec("h5py") is not None


class AngleSelectionTests(unittest.TestCase):
    def test_single_angle_selects_center_transmit(self):
        np.testing.assert_array_equal(_select_angles(75, 1), np.array([37]))

    def test_angle_selection_includes_both_extremes(self):
        selected = _select_angles(75, 11)
        self.assertEqual(selected.size, 11)
        self.assertEqual(selected[0], 0)
        self.assertEqual(selected[-1], 74)

    def test_invalid_angle_count_is_rejected(self):
        with self.assertRaises(ValueError):
            _select_angles(75, 76)

    def test_single_plane_wave_rejects_invalid_index(self):
        acquisition = type("Acquisition", (), {"transmit_angles_rad": np.zeros(2)})()
        with self.assertRaises(IndexError):
            beamform_plane_wave(acquisition, 2, np.zeros(1), np.ones(1))


@unittest.skipUnless(HAS_H5PY and DATASET.is_file(), "PICMUS UFF dataset not installed")
class InstalledDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ultrasound_bmode.real_data import load_picmus_uff

        cls.acquisition = load_picmus_uff(DATASET)

    def test_uff_dimensions_and_metadata(self):
        acquisition = self.acquisition
        self.assertEqual(acquisition.channel_data.shape, (75, 128, 1536))
        self.assertEqual(acquisition.reference_iq.shape, (609, 387))
        self.assertAlmostEqual(acquisition.sampling_frequency_hz, 20.832e6)
        self.assertEqual(acquisition.element_x_m.size, 128)

    def test_coarse_real_reconstruction_is_finite(self):
        from ultrasound_bmode.real_data import plane_wave_delay_and_sum

        result = plane_wave_delay_and_sum(
            self.acquisition,
            angle_count=1,
            lateral_stride=40,
            axial_stride=40,
        )
        self.assertTrue(np.isfinite(result.bmode_db).all())
        self.assertEqual(result.angle_indices.size, 1)
