"""Dataset-independent envelope and accelerated-backend regression tests."""

import unittest

import numpy as np

from ultrasound_bmode.accelerated import numba_available, numba_plane_wave_delay_and_sum
from ultrasound_bmode.real_data import (
    UFFAcquisition,
    beamform_plane_wave,
    plane_wave_delay_and_sum,
)


def pulse_acquisition():
    fs = 40e6
    speed = 1540.0
    samples = np.arange(2048)
    envelope = np.exp(-0.5 * ((samples - 1024) / 90) ** 2)
    signal = envelope * np.cos(2 * np.pi * 5e6 * samples / fs)
    return UFFAcquisition(
        channel_data=signal[None, None, :],
        sampling_frequency_hz=fs,
        sound_speed_m_s=speed,
        initial_time_s=0.0,
        element_x_m=np.array([0.0]),
        transmit_angles_rad=np.array([0.0]),
        x_axis_m=np.array([0.0]),
        z_axis_m=np.arange(512, 1536) / fs * speed / 2,
        reference_iq=None,
        name="Synthetic Gaussian pulse (test fixture, not patient data)",
        citation="Analytical Gaussian envelope",
    )


class AnalyticEnvelopeTests(unittest.TestCase):
    def test_recovers_known_envelope_on_undersampled_depth_grid(self):
        acquisition = pulse_acquisition()
        result = plane_wave_delay_and_sum(
            acquisition, angle_count=1, lateral_stride=1, axial_stride=8, analytic=True
        )
        samples = np.arange(512, 1536, 8)
        expected = np.exp(-0.5 * ((samples - 1024) / 90) ** 2)
        np.testing.assert_allclose(np.abs(result.rf[:, 0]), expected, atol=1e-9)
        legacy = plane_wave_delay_and_sum(
            acquisition, angle_count=1, lateral_stride=1, axial_stride=8
        )
        # This carrier aliases to DC on the coarse grid. Output-grid Hilbert
        # invents a quadrature component from the envelope instead of the RF.
        from ultrasound_bmode.processing import envelope_detect

        self.assertGreater(np.max(np.abs(envelope_detect(legacy.rf)[:, 0] - expected)), 0.1)

    def test_complex_rf_is_invariant_to_output_grid_subsampling(self):
        acquisition = pulse_acquisition()
        fine = plane_wave_delay_and_sum(
            acquisition, angle_count=1, lateral_stride=1, axial_stride=1, analytic=True
        )
        coarse = plane_wave_delay_and_sum(
            acquisition, angle_count=1, lateral_stride=1, axial_stride=7, analytic=True
        )
        np.testing.assert_allclose(coarse.rf, fine.rf[::7], rtol=1e-12, atol=1e-12)
        self.assertTrue(np.iscomplexobj(coarse.rf))

    def test_signed_dmas_rejects_analytic_mode_at_both_entrypoints(self):
        acquisition = pulse_acquisition()
        with self.assertRaisesRegex(ValueError, "signed real DMAS"):
            plane_wave_delay_and_sum(acquisition, angle_count=1, method="dmas", analytic=True)
        with self.assertRaisesRegex(ValueError, "signed real DMAS"):
            beamform_plane_wave(
                acquisition, 0, acquisition.x_axis_m, acquisition.z_axis_m,
                method="dmas", analytic=True,
            )

    @unittest.skipUnless(numba_available(), "Numba extra not installed")
    def test_numba_matches_numpy_with_delays_angles_and_invalid_samples(self):
        from dataclasses import replace

        base = pulse_acquisition()
        rng = np.random.default_rng(42)
        acquisition = replace(
            base,
            channel_data=rng.normal(size=(5, 7, 2048)).astype(np.float32),
            element_x_m=np.linspace(-2e-3, 2e-3, 7),
            transmit_angles_rad=np.array([0.0, 0.15, -0.15, 0.07, -0.07]),
            x_axis_m=np.linspace(-3e-3, 3e-3, 9),
            z_axis_m=np.linspace(0.0, 50e-3, 35),
            initial_time_s=1.25e-6,
        )
        for analytic in (False, True):
            for angle_count in (1, 3, 5):
                with self.subTest(analytic=analytic, angle_count=angle_count):
                    kwargs = {"angle_count": angle_count, "analytic": analytic}
                    expected = plane_wave_delay_and_sum(acquisition, **kwargs)
                    actual = numba_plane_wave_delay_and_sum(acquisition, **kwargs)
                    np.testing.assert_array_equal(actual.angle_indices, expected.angle_indices)
                    np.testing.assert_allclose(actual.rf, expected.rf, rtol=1e-5, atol=1e-7)
                    np.testing.assert_allclose(actual.bmode_db, expected.bmode_db, atol=1e-4)


if __name__ == "__main__":
    unittest.main()
