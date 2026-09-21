import importlib.util
import unittest

import numpy as np

HAS_NUMBA = importlib.util.find_spec("numba") is not None


@unittest.skipUnless(HAS_NUMBA, "Numba acceleration extra not installed")
class AcceleratedBackendTests(unittest.TestCase):
    def test_numba_kernel_matches_numpy_on_coarse_real_grid(self):
        from pathlib import Path

        from ultrasound_bmode.accelerated import numba_plane_wave_delay_and_sum
        from ultrasound_bmode.real_data import load_picmus_uff, plane_wave_delay_and_sum

        path = Path("data/raw/PICMUS_carotid_cross.uff")
        if not path.is_file():
            self.skipTest("PICMUS UFF dataset not installed")
        acquisition = load_picmus_uff(path)
        expected = plane_wave_delay_and_sum(
            acquisition, angle_count=1, lateral_stride=80, axial_stride=80
        )
        actual = numba_plane_wave_delay_and_sum(
            acquisition, angle_count=1, lateral_stride=80, axial_stride=80
        )
        np.testing.assert_allclose(actual.rf, expected.rf, rtol=1e-5, atol=1e-7)
