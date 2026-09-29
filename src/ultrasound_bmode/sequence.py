"""Bounded frame access for a validated, single-plane-wave RF UFF sequence."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from .real_data import UFFAcquisition


class UFFPlaneWaveSequence:
    """Context-managed reader; never materializes the complete four-dimensional RF array.

    This intentionally supports only the SWE L7 single-wave layout, not arbitrary UFF.
    Frame index preserves storage order; no acquisition frame rate is inferred.
    """

    def __init__(self, path, lateral_pixels=128, axial_pixels=256, maximum_depth_m=0.055):
        if any(isinstance(n, bool) or not isinstance(n, int) or n < 2
               for n in (lateral_pixels, axial_pixels)):
            raise ValueError("grid sizes must be integers >= 2")
        if not np.isfinite(maximum_depth_m) or maximum_depth_m <= 0.002:
            raise ValueError("maximum depth must exceed 2 mm")
        self.path = Path(path)
        self._file = h5py.File(self.path, "r")
        try:
            group = self._file["channel_data"]
            self._data = group["data"]
            if (self._data.ndim != 4 or self._data.shape[1] != 1
                    or min(self._data.shape) < 1 or self._data.shape[-1] < 4
                    or self._data.dtype not in (np.dtype("float32"), np.dtype("float64"))):
                raise ValueError("expected real [frame, 1, element, sample] float RF data")
            self.frame_count = self._data.shape[0]
            self.shape = self._data.shape
            self.dtype = self._data.dtype

            def scalar(key):
                array = np.asarray(group[key])
                if array.size != 1:
                    raise ValueError(f"expected scalar {key}")
                return float(array.item())

            self.fs = scalar("sampling_frequency")
            self.c = scalar("sound_speed")
            self.initial_time = scalar("initial_time")
            self.wave_delay = scalar("sequence/delay")
            self.angle = scalar("sequence/source/azimuth")
            finite = [self.fs, self.c, self.initial_time, self.wave_delay, self.angle]
            if not np.isfinite(finite).all() or self.fs <= 0 or self.c <= 0:
                raise ValueError("invalid RF timing or sound speed")
            if scalar("modulation_frequency") != 0:
                raise ValueError("baseband IQ is unsupported; real RF is required")
            if (scalar("sequence/source/distance") != np.inf
                    or scalar("sequence/source/elevation") != 0
                    or not np.isclose(scalar("sequence/sound_speed"), self.c)):
                raise ValueError("requires a planar wave with matching transmit/receive speed")
            geometry = np.asarray(group["probe/geometry"])
            if (geometry.ndim != 2 or geometry.shape[0] < 3
                    or geometry.shape[1] != self.shape[2]
                    or not np.isfinite(geometry[:3]).all()
                    or not np.allclose(geometry[1:3], 0, atol=1e-12, rtol=0)):
                raise ValueError("requires a linear probe in the z=0, y=0 plane")
            self.elements = geometry[0].astype(float)
            if np.ptp(self.elements) <= 0:
                raise ValueError("probe must span a nonzero lateral aperture")
            self.x = np.linspace(self.elements.min(), self.elements.max(), lateral_pixels)
            self.z = np.linspace(0.002, maximum_depth_m, axial_pixels)
        except BaseException:
            self.close()
            raise

    @property
    def effective_initial_time_s(self):
        # USTB DAS: transmit/c - wave.delay + receive/c - channel.initial_time.
        return self.initial_time + self.wave_delay

    def read_frame(self, index):
        if not self._file.id.valid:
            raise RuntimeError("sequence is closed")
        if isinstance(index, bool) or not isinstance(index, (int, np.integer)):
            raise TypeError("frame index must be an integer")
        if not 0 <= index < self.frame_count:
            raise IndexError("frame index outside sequence")
        channel = np.asarray(self._data[index])
        if not np.isfinite(channel).all():
            raise ValueError("non-finite RF samples")
        return UFFAcquisition(
            channel, self.fs, self.c, self.effective_initial_time_s,
            self.elements.copy(), np.array([self.angle]), self.x.copy(), self.z.copy(),
            None, f"{self.path.name}: frame {index}",
            "USTB dataset archive, Zenodo record 20261898; specimen not established",
        )

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
