import unittest

import numpy as np

from ultrasound_bmode.accelerated import numba_available, numba_plane_wave_delay_and_sum
from ultrasound_bmode.real_data import UFFAcquisition, plane_wave_delay_and_sum


def fixture():
    rng = np.random.default_rng(17)
    return UFFAcquisition(
        channel_data=rng.normal(size=(7, 5, 768)).astype(np.float32),
        sampling_frequency_hz=20e6, sound_speed_m_s=1540.0, initial_time_s=-0.3e-6,
        element_x_m=np.linspace(-1e-3, 1e-3, 5),
        transmit_angles_rad=np.array([0, 0.2, -0.2, 0.1, -0.1, 0.05, -0.05]),
        x_axis_m=np.linspace(-2e-3, 2e-3, 9), z_axis_m=np.linspace(1e-3, 25e-3, 30),
        reference_iq=None, name="Batching test fixture", citation="Synthetic random channels",
    )


@unittest.skipUnless(numba_available(), "Numba extra not installed")
class AngleBatchingTests(unittest.TestCase):
    def test_partial_batches_match_numpy_for_real_and_complex_outputs(self):
        acquisition = fixture()
        for analytic in (False, True):
            for count in (1, 5, 7):
                expected = plane_wave_delay_and_sum(acquisition, angle_count=count, analytic=analytic)
                for batch in (1, 2, 3, 7, 20, None):
                    with self.subTest(analytic=analytic, count=count, batch=batch):
                        actual = numba_plane_wave_delay_and_sum(
                            acquisition, angle_count=count, analytic=analytic, angle_batch_size=batch
                        )
                        np.testing.assert_array_equal(actual.angle_indices, expected.angle_indices)
                        np.testing.assert_allclose(actual.rf, expected.rf, rtol=1e-5, atol=1e-7)
                        np.testing.assert_allclose(actual.bmode_db, expected.bmode_db, atol=1e-4)

    def test_batching_preserves_selected_input_channels(self):
        acquisition = fixture()
        before = acquisition.channel_data.copy()
        numba_plane_wave_delay_and_sum(acquisition, angle_count=5, analytic=True, angle_batch_size=2)
        np.testing.assert_array_equal(before, acquisition.channel_data)

    def test_invalid_batch_sizes_are_rejected(self):
        for batch in (0, -1, 1.5, True, "2"):
            with self.subTest(batch=batch), self.assertRaisesRegex(ValueError, "angle_batch_size"):
                numba_plane_wave_delay_and_sum(fixture(), angle_count=1, angle_batch_size=batch)


if __name__ == "__main__":
    unittest.main()
