import unittest
from dataclasses import replace

import numpy as np
from scipy.signal import hilbert

from ultrasound_bmode.accelerated import (
    AnalyticChannelCache,
    numba_available,
    numba_plane_wave_delay_and_sum,
    prepare_analytic_channel_cache,
)
from ultrasound_bmode.real_data import UFFAcquisition


def fixture(seed=55):
    rng = np.random.default_rng(seed)
    return UFFAcquisition(
        channel_data=rng.normal(size=(7, 5, 768)).astype(np.float32),
        sampling_frequency_hz=20e6, sound_speed_m_s=1540.0, initial_time_s=0.0,
        element_x_m=np.linspace(-1e-3, 1e-3, 5),
        transmit_angles_rad=np.linspace(-0.2, 0.2, 7),
        x_axis_m=np.linspace(-2e-3, 2e-3, 9), z_axis_m=np.linspace(2e-3, 25e-3, 25),
        reference_iq=None, name="Cache fixture", citation="Synthetic random channels",
    )


class AnalyticCacheTests(unittest.TestCase):
    def test_preparation_matches_full_hilbert_and_is_read_only(self):
        acquisition = fixture()
        for batch in (1, 3, 20):
            with self.subTest(batch=batch):
                cache = prepare_analytic_channel_cache(acquisition, batch)
                np.testing.assert_allclose(
                    cache.quadrature, hilbert(acquisition.channel_data, axis=-1).imag,
                    rtol=1e-6, atol=5e-7,
                )
                self.assertIs(cache.source_channel_data, acquisition.channel_data)
                self.assertFalse(cache.quadrature.flags.writeable)
                self.assertEqual(cache.preparation_batch_size, batch)
                self.assertGreater(cache.preparation_seconds, 0)
                self.assertAlmostEqual(cache.size_mib, cache.quadrature.nbytes / 2**20)

    def test_invalid_preparation_inputs_are_rejected(self):
        acquisition = fixture()
        for batch in (0, -1, 1.5, True, "2"):
            with self.subTest(batch=batch), self.assertRaisesRegex(ValueError, "batch_size"):
                prepare_analytic_channel_cache(acquisition, batch)
        malformed = replace(acquisition, channel_data=acquisition.channel_data.astype(np.int16))
        with self.assertRaisesRegex(ValueError, "real floating"):
            prepare_analytic_channel_cache(malformed)

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_cached_and_uncached_outputs_match_for_multiple_selections(self):
        acquisition = fixture()
        cache = prepare_analytic_channel_cache(acquisition, 2)
        for count, batch in ((1, 1), (5, 2), (7, 3), (7, None)):
            with self.subTest(count=count, batch=batch):
                expected = numba_plane_wave_delay_and_sum(
                    acquisition, angle_count=count, analytic=True, angle_batch_size=batch
                )
                actual = numba_plane_wave_delay_and_sum(
                    acquisition, angle_count=count, analytic=True, angle_batch_size=batch,
                    analytic_cache=cache,
                )
                np.testing.assert_array_equal(actual.angle_indices, expected.angle_indices)
                np.testing.assert_allclose(actual.rf, expected.rf, rtol=1e-6, atol=1e-8)
                np.testing.assert_allclose(actual.bmode_db, expected.bmode_db, atol=1e-5)

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_cache_cannot_be_silently_reused_for_another_array(self):
        acquisition = fixture()
        cache = prepare_analytic_channel_cache(acquisition)
        other = fixture(seed=56)
        with self.assertRaisesRegex(ValueError, "different channel_data"):
            numba_plane_wave_delay_and_sum(
                other, analytic=True, analytic_cache=cache, angle_count=1
            )
        with self.assertRaisesRegex(ValueError, "requires analytic=True"):
            numba_plane_wave_delay_and_sum(
                acquisition, analytic=False, analytic_cache=cache, angle_count=1
            )
        with self.assertRaisesRegex(TypeError, "AnalyticChannelCache"):
            numba_plane_wave_delay_and_sum(
                acquisition, analytic=True, analytic_cache=object(), angle_count=1
            )

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_corrupt_cache_shape_and_dtype_are_rejected(self):
        acquisition = fixture()
        cache = prepare_analytic_channel_cache(acquisition)
        wrong_shape = AnalyticChannelCache(
            acquisition.channel_data, cache.quadrature[:, :, :-1], 0.1, 8
        )
        wrong_dtype = AnalyticChannelCache(
            acquisition.channel_data, cache.quadrature.astype(np.float64), 0.1, 8
        )
        for invalid, message in ((wrong_shape, "shape"), (wrong_dtype, "dtype")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                numba_plane_wave_delay_and_sum(
                    acquisition, analytic=True, analytic_cache=invalid, angle_count=1
                )


if __name__ == "__main__":
    unittest.main()
