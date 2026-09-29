import unittest
from dataclasses import replace

import numpy as np

from ultrasound_bmode.native_backend import (
    native_available,
    native_build_info,
    native_library_path,
    native_plane_wave_delay_and_sum,
)
from ultrasound_bmode.real_data import UFFAcquisition, plane_wave_delay_and_sum


def acquisition_fixture(dtype=np.float32):
    rng = np.random.default_rng(57)
    return UFFAcquisition(
        (rng.normal(size=(7, 5, 768))*10000).astype(dtype), 20e6, 1540, 1.375e-6,
        np.linspace(-0.002, 0.002, 5),
        np.array([0.0, 0.21, -0.18, 0.07, -0.06, 0.14, -0.12]),
        np.linspace(-0.004, 0.004, 7), np.linspace(0, 0.035, 19), None,
        "synthetic high-amplitude RF", "deterministic unit fixture",
    )


class NativeBackendTests(unittest.TestCase):
    def test_availability_matches_library_path(self):
        self.assertEqual(native_available(), native_library_path() is not None)

    @unittest.skipUnless(native_available(), "C++ library not built")
    def test_analytic_legacy_linear_cubic_dtype_batch_parity(self):
        self.assertIn("openmp", native_build_info())
        for dtype in (np.float32, np.float64):
            acquisition = acquisition_fixture(dtype)
            for interpolation in ("linear", "cubic"):
                for analytic in (False, True):
                    for count, batch in ((1, 1), (5, 2), (7, 3)):
                        with self.subTest(dtype=dtype, interpolation=interpolation,
                                          analytic=analytic, count=count):
                            kwargs = {"angle_count": count, "lateral_stride": 1,
                                      "axial_stride": 1, "analytic": analytic,
                                      "interpolation": interpolation}
                            expected = plane_wave_delay_and_sum(acquisition, **kwargs)
                            actual = native_plane_wave_delay_and_sum(
                                acquisition, angle_batch_size=batch, threads=2, **kwargs)
                            np.testing.assert_array_equal(actual.angle_indices, expected.angle_indices)
                            np.testing.assert_allclose(actual.rf, expected.rf, rtol=1e-5, atol=1e-7)
                            np.testing.assert_allclose(actual.bmode_db, expected.bmode_db,
                                                       rtol=0, atol=1e-4)

    @unittest.skipUnless(native_available(), "C++ library not built")
    def test_cubic_stencil_and_large_float32_offset(self):
        samples = 1e8 + 8*np.arange(32, dtype=np.float32)
        positions = np.array([-1, 0, 0.5, 1, 1.25, 5, 20.75, 29.75, 30, 31])
        acquisition = UFFAcquisition(
            samples[None, None], 1, 2, 8, np.array([0.0]), np.array([0.0]),
            np.array([0.0]), positions+8, None, "boundary", "synthetic",
        )
        actual = native_plane_wave_delay_and_sum(
            acquisition, angle_count=1, lateral_stride=1, axial_stride=1, interpolation="cubic")
        expected = np.where((positions >= 1) & (positions < 30), 1e8+8*positions, 0)
        np.testing.assert_allclose(actual.rf[:, 0], expected, rtol=0, atol=1e-7)

    def test_invalid_inputs_rejected_before_native_call(self):
        acquisition = acquisition_fixture()
        for kwargs in ({"angle_count": 0}, {"angle_batch_size": 0}, {"threads": 0},
                       {"lateral_stride": 1.5}, {"f_number": np.nan},
                       {"interpolation": "nearest"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                native_plane_wave_delay_and_sum(acquisition, **kwargs)
        for change in ({"element_x_m": np.array([0])}, {"sampling_frequency_hz": -1},
                       {"channel_data": acquisition.channel_data.astype(complex)},
                       {"x_axis_m": np.array([np.nan])}):
            with self.subTest(change=list(change)), self.assertRaises(ValueError):
                native_plane_wave_delay_and_sum(replace(acquisition, **change), angle_count=1)
