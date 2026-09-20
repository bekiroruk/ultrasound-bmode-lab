import unittest

import numpy as np

from ultrasound_bmode.beamforming import delay_and_sum
from ultrasound_bmode.config import ImagingConfig


class BeamformingTests(unittest.TestCase):
    def test_delay_and_sum_focuses_impulse_on_expected_depth(self):
        config = ImagingConfig(
            element_count=8, line_count=1, depth_samples=220, max_depth_m=35e-3
        )
        channel = np.zeros((1, config.element_count, config.rf_sample_count), dtype=np.float32)
        target_depth = 20e-3
        for element_index, element_x in enumerate(config.element_positions_m):
            delay = (target_depth + np.hypot(element_x, target_depth)) / config.sound_speed_m_s
            sample = int(round(delay * config.sampling_frequency_hz))
            channel[0, element_index, sample] = 1.0
        beamformed = delay_and_sum(channel, config)
        estimated_depth = config.depth_axis_m[np.argmax(beamformed[:, 0])]
        axial_sample_spacing = np.diff(config.depth_axis_m).mean()
        self.assertLessEqual(abs(estimated_depth - target_depth), 2.0 * axial_sample_spacing)


    def test_beamformer_rejects_wrong_shape(self):
        config = ImagingConfig(element_count=8, line_count=1)
        bad = np.zeros((1, 7, config.rf_sample_count), dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "Expected channel data shape"):
            delay_and_sum(bad, config)
