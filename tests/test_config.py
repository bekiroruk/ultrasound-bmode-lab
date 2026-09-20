import unittest

from ultrasound_bmode.config import ImagingConfig


class ConfigTests(unittest.TestCase):
    def test_nyquist_validation(self):
        with self.assertRaisesRegex(ValueError, "Nyquist"):
            ImagingConfig(center_frequency_hz=10e6, sampling_frequency_hz=15e6)


    def test_axes_match_declared_sizes(self):
        config = ImagingConfig(element_count=12, line_count=17, depth_samples=91)
        self.assertEqual(config.element_positions_m.size, 12)
        self.assertEqual(config.line_positions_m.size, 17)
        self.assertEqual(config.depth_axis_m.size, 91)
