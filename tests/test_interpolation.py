import unittest
from dataclasses import replace

import numpy as np

from ultrasound_bmode.accelerated import (
    numba_available,
    numba_plane_wave_delay_and_sum,
    prepare_analytic_channel_cache,
)
from ultrasound_bmode.real_data import (
    UFFAcquisition,
    beamform_plane_wave,
    plane_wave_delay_and_sum,
)


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


def exact_position_fixture(samples, positions):
    """Use binary-exact geometry: sample position = depth - initial_time."""
    return UFFAcquisition(
        channel_data=np.asarray(samples)[None, None, :],
        sampling_frequency_hz=1.0,
        sound_speed_m_s=2.0,
        initial_time_s=8.0,
        element_x_m=np.array([0.0]),
        transmit_angles_rad=np.array([0.0]),
        x_axis_m=np.array([0.0]),
        z_axis_m=np.asarray(positions) + 8.0,
        reference_iq=None,
        name="Exact fractional-delay fixture",
        citation="Analytical synthetic fixture",
    )


class DelayInterpolationTests(unittest.TestCase):
    def test_cubic_reproduces_constant_linear_and_quadratic_signals(self):
        # Catmull-Rom reproduces these polynomials, not general cubics.
        positions = np.arange(1.0, 29.0, 0.125)
        for dtype in (np.float32, np.float64):
            samples = np.arange(32, dtype=dtype)
            for power in (0, 1, 2):
                with self.subTest(dtype=dtype, power=power):
                    acquisition = exact_position_fixture(samples**power, positions)
                    actual = beamform_plane_wave(
                        acquisition, 0, acquisition.x_axis_m, acquisition.z_axis_m,
                        interpolation="cubic",
                    )[:, 0]
                    np.testing.assert_allclose(actual, positions**power, rtol=0, atol=1e-12)

    def test_cubic_preserves_small_float32_variation_on_large_offset(self):
        # Every input is exactly representable in float32. Forming the cubic
        # coefficients in float32 used to lose up to 12.25 despite the linear data.
        positions = np.arange(3.125, 20, 0.25)
        samples = 1e8 + 8 * np.arange(32, dtype=np.float32)
        acquisition = exact_position_fixture(samples, positions)
        backends = [plane_wave_delay_and_sum]
        if numba_available():
            backends.append(numba_plane_wave_delay_and_sum)
        for backend in backends:
            with self.subTest(backend=backend.__name__):
                actual = backend(
                    acquisition, angle_count=1, lateral_stride=1, axial_stride=1,
                    interpolation="cubic",
                ).rf[:, 0]
                np.testing.assert_allclose(actual, 1e8 + 8 * positions, rtol=0, atol=1e-7)

    def test_integer_samples_and_full_stencil_support_boundaries(self):
        # Cubic requires floor(t)-1 .. floor(t)+2, so t=1 is supported,
        # t=n-2 is not. Linear retains its existing [0,n-1) support.
        positions = np.array([-1, 0, 0.5, 1, 1.25, 5, 6, 6.75, 7, 7.5, 8, 9, 10, 12])
        samples = 2 * np.arange(10, dtype=float) + 3
        acquisition = exact_position_fixture(samples, positions)
        backends = [plane_wave_delay_and_sum]
        if numba_available():
            backends.append(numba_plane_wave_delay_and_sum)
        for interpolation, start, stop in (("linear", 0, 9), ("cubic", 1, 8)):
            supported = (positions >= start) & (positions < stop)
            expected = np.where(supported, 2 * positions + 3, 0)
            for backend in backends:
                with self.subTest(interpolation=interpolation, backend=backend.__name__):
                    actual = backend(
                        acquisition, angle_count=1, lateral_stride=1, axial_stride=1,
                        interpolation=interpolation,
                    ).rf[:, 0]
                    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)

    def test_out_of_support_channel_is_excluded_from_normalizer(self):
        acquisition = exact_position_fixture(np.full(16, 3.0), [12.0, 16.0])
        acquisition = replace(
            acquisition,
            channel_data=np.stack([np.full(16, 3.0), np.full(16, 99.0)])[None],
            element_x_m=np.array([0.0, 16.0]),
        )
        # At depth 20 the central channel is supported, but the longer off-axis
        # path leaves the cubic stencil. At depth 24 neither channel is supported.
        backends = [plane_wave_delay_and_sum]
        if numba_available():
            backends.append(numba_plane_wave_delay_and_sum)
        for backend in backends:
            with self.subTest(backend=backend.__name__):
                result = backend(
                    acquisition, angle_count=1, lateral_stride=1, axial_stride=1,
                    f_number=0.25, interpolation="cubic",
                )
                np.testing.assert_allclose(result.rf[:, 0], [3.0, 0.0], rtol=0, atol=1e-12)

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
    def test_numba_cubic_matches_numpy_with_angles_batches_and_cache(self):
        rng = np.random.default_rng(209)
        base, _ = sinusoid_fixture()
        for dtype in (np.float32, np.float64):
            acquisition = replace(
                base,
                channel_data=rng.normal(size=(7, 5, 768)).astype(dtype),
                sampling_frequency_hz=20e6,
                initial_time_s=1.375e-6,
                transmit_angles_rad=np.array([0.0, 0.21, -0.18, 0.07, -0.06, 0.14, -0.12]),
                element_x_m=np.linspace(-2e-3, 2e-3, 5),
                x_axis_m=np.linspace(-4e-3, 4e-3, 7),
                z_axis_m=np.linspace(0, 35e-3, 19),
            )
            cache = prepare_analytic_channel_cache(acquisition, batch_size=3)
            for count, batch in ((1, 1), (5, 2), (7, 3)):
                for analytic in (False, True):
                    kwargs = {
                        "angle_count": count, "lateral_stride": 1, "axial_stride": 1,
                        "analytic": analytic, "interpolation": "cubic",
                    }
                    expected = plane_wave_delay_and_sum(acquisition, **kwargs)
                    caches = (None, cache) if analytic else (None,)
                    for current_cache in caches:
                        with self.subTest(
                            dtype=dtype, count=count, batch=batch, analytic=analytic,
                            cached=current_cache is not None,
                        ):
                            actual = numba_plane_wave_delay_and_sum(
                                acquisition, angle_batch_size=batch,
                                analytic_cache=current_cache, **kwargs,
                            )
                            np.testing.assert_array_equal(
                                actual.angle_indices, expected.angle_indices
                            )
                            np.testing.assert_allclose(
                                actual.rf, expected.rf, rtol=1e-5, atol=1e-7
                            )
                            np.testing.assert_allclose(
                                actual.bmode_db, expected.bmode_db, rtol=0, atol=1e-4
                            )


if __name__ == "__main__":
    unittest.main()
