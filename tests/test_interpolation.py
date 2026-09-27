import unittest
from dataclasses import replace

import numpy as np

from ultrasound_bmode.accelerated import numba_available, numba_plane_wave_delay_and_sum
from ultrasound_bmode.real_data import UFFAcquisition, plane_wave_delay_and_sum


def sinusoid_fixture():
    sampling_frequency = 40e6
    sound_speed = 1540.0
    sample_axis = np.arange(256)
    channel = np.cos(2 * np.pi * 5e6 * sample_axis / sampling_frequency)[None, None, :]
    sample_positions = np.arange(80.1, 180.0, 0.37)
    acquisition = UFFAcquisition(
        channel_data=channel,
        sampling_frequency_hz=sampling_frequency,
        sound_speed_m_s=sound_speed,
        initial_time_s=0.0,
        element_x_m=np.array([0.0]),
        transmit_angles_rad=np.array([0.0]),
        x_axis_m=np.array([0.0]),
        z_axis_m=sample_positions * sound_speed / (2 * sampling_frequency),
        reference_iq=None,
        name="Fractional-delay sinusoid fixture",
        citation="Analytical synthetic fixture",
    )
    expected = np.cos(2 * np.pi * 5e6 * sample_positions / sampling_frequency)
    return acquisition, expected


class DelayInterpolationTests(unittest.TestCase):
    def test_cubic_reduces_fractional_delay_error_for_bandlimited_sinusoid(self):
        acquisition, expected = sinusoid_fixture()
        linear = plane_wave_delay_and_sum(
            acquisition, angle_count=1, lateral_stride=1, axial_stride=1,
            interpolation="linear",
        ).rf[:, 0]
        cubic = plane_wave_delay_and_sum(
            acquisition, angle_count=1, lateral_stride=1, axial_stride=1,
            interpolation="cubic",
        ).rf[:, 0]
        linear_rmse = float(np.sqrt(np.mean((linear - expected) ** 2)))
        cubic_rmse = float(np.sqrt(np.mean((cubic - expected) ** 2)))
        self.assertLess(cubic_rmse, linear_rmse * 0.2)

    def test_invalid_method_and_short_cubic_input_are_rejected(self):
        acquisition, _ = sinusoid_fixture()
        with self.assertRaisesRegex(ValueError, "interpolation"):
            plane_wave_delay_and_sum(acquisition, angle_count=1, interpolation="nearest")
        short = replace(acquisition, channel_data=acquisition.channel_data[..., :3])
        with self.assertRaisesRegex(ValueError, "at least four"):
            plane_wave_delay_and_sum(short, angle_count=1, interpolation="cubic")

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_numba_cubic_matches_numpy_for_real_and_analytic_rf(self):
        acquisition, _ = sinusoid_fixture()
        acquisition = replace(
            acquisition,
            channel_data=np.repeat(acquisition.channel_data.astype(np.float32), 3, axis=1),
            element_x_m=np.linspace(-0.5e-3, 0.5e-3, 3),
        )
        for analytic in (False, True):
            expected = plane_wave_delay_and_sum(
                acquisition, angle_count=1, lateral_stride=1, axial_stride=1,
                analytic=analytic, interpolation="cubic",
            )
            actual = numba_plane_wave_delay_and_sum(
                acquisition, angle_count=1, lateral_stride=1, axial_stride=1,
                analytic=analytic, interpolation="cubic",
            )
            np.testing.assert_allclose(actual.rf, expected.rf, rtol=1e-5, atol=1e-7)
            np.testing.assert_allclose(actual.bmode_db, expected.bmode_db, atol=1e-4)


if __name__ == "__main__":
    unittest.main()
