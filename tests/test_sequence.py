import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from ultrasound_bmode.sequence import UFFPlaneWaveSequence


def write_sequence(path):
    with h5py.File(path, "w") as f:
        g = f.create_group("channel_data")
        g["data"] = np.arange(3*1*2*16, dtype=np.float32).reshape(3, 1, 2, 16)
        for key, value in {
            "sampling_frequency": 20e6, "sound_speed": 1540, "initial_time": 2e-6,
            "modulation_frequency": 0, "sequence/delay": -1e-6,
            "sequence/source/azimuth": 0, "sequence/source/distance": np.inf,
            "sequence/source/elevation": 0, "sequence/sound_speed": 1540,
        }.items():
            g[key] = np.array([[value]], dtype=float)
        g["probe/geometry"] = [[-0.001, 0.001], [0, 0], [0, 0]]


class SequenceTests(unittest.TestCase):
    def test_lazy_frames_timing_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.uff"
            write_sequence(path)
            with UFFPlaneWaveSequence(path, 4, 8) as sequence:
                self.assertIsInstance(sequence._data, h5py.Dataset)
                self.assertEqual(sequence.frame_count, 3)
                first, last = sequence.read_frame(0), sequence.read_frame(2)
                self.assertEqual(first.channel_data.shape, (1, 2, 16))
                np.testing.assert_array_equal(last.channel_data-first.channel_data, 64)
                self.assertEqual(first.initial_time_s, 1e-6)
                self.assertEqual(first.z_axis_m.size, 8)
                for index in (-1, 3):
                    with self.assertRaises(IndexError):
                        sequence.read_frame(index)
                with self.assertRaises(TypeError):
                    sequence.read_frame(0.5)
            with self.assertRaises(RuntimeError):
                sequence.read_frame(0)

    def test_unsupported_physics_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.uff"
            for key, value in (("sequence/source/distance", 1.0),
                               ("modulation_frequency", 5e6),
                               ("sequence/source/elevation", 0.1),
                               ("sampling_frequency", -1),
                               ("sequence/delay", np.nan)):
                write_sequence(path)
                with h5py.File(path, "r+") as f:
                    f["channel_data/" + key][...] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    UFFPlaneWaveSequence(path)
