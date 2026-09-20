"""Validated acquisition and reconstruction configuration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImagingConfig:
    """Physical and numerical parameters, expressed in SI units."""

    sound_speed_m_s: float = 1540.0
    center_frequency_hz: float = 5.0e6
    sampling_frequency_hz: float = 20.0e6
    fractional_bandwidth: float = 0.65
    element_count: int = 32
    element_pitch_m: float = 0.30e-3
    line_count: int = 48
    image_width_m: float = 28.0e-3
    max_depth_m: float = 50.0e-3
    depth_samples: int = 384
    f_number: float = 1.5
    dynamic_range_db: float = 60.0
    tgc_db_cm_mhz: float = 0.5

    def __post_init__(self) -> None:
        positive = {
            "sound_speed_m_s": self.sound_speed_m_s,
            "center_frequency_hz": self.center_frequency_hz,
            "sampling_frequency_hz": self.sampling_frequency_hz,
            "element_count": self.element_count,
            "line_count": self.line_count,
            "max_depth_m": self.max_depth_m,
            "depth_samples": self.depth_samples,
            "f_number": self.f_number,
            "dynamic_range_db": self.dynamic_range_db,
        }
        invalid = [name for name, value in positive.items() if value <= 0]
        if invalid:
            raise ValueError(f"Parameters must be positive: {', '.join(invalid)}")
        if self.sampling_frequency_hz < 2 * self.center_frequency_hz:
            raise ValueError("Sampling frequency must satisfy the Nyquist criterion")
        if not 0 < self.fractional_bandwidth <= 2:
            raise ValueError("fractional_bandwidth must be in (0, 2]")

    @property
    def element_positions_m(self):
        import numpy as np

        indices = np.arange(self.element_count) - (self.element_count - 1) / 2
        return indices * self.element_pitch_m

    @property
    def line_positions_m(self):
        import numpy as np

        if self.line_count == 1:
            return np.array([0.0])
        return np.linspace(-self.image_width_m / 2, self.image_width_m / 2, self.line_count)

    @property
    def depth_axis_m(self):
        import numpy as np

        return np.linspace(0.5e-3, self.max_depth_m, self.depth_samples)

    @property
    def rf_sample_count(self) -> int:
        # Covers the longest two-way path with a small guard interval.
        aperture_half = self.element_count * self.element_pitch_m / 2
        longest_path = self.max_depth_m + (self.max_depth_m**2 + aperture_half**2) ** 0.5
        return int(longest_path / self.sound_speed_m_s * self.sampling_frequency_hz) + 64
