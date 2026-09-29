"""Validated ctypes bridge to C++17/OpenMP linear or cubic analytic-RF DAS."""

from __future__ import annotations

import ctypes
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.signal import hilbert

from .processing import envelope_detect, log_compress
from .real_data import (
    PlaneWaveResult,
    UFFAcquisition,
    _validate_delay_interpolation,
    select_transmit_indices,
)


def _library_candidates() -> tuple[Path, ...]:
    root = Path(__file__).resolve().parents[2]
    return (
        root / "native/build/Release/ultrasound_native.dll",
        root / "native/build/ultrasound_native.dll",
        root / "native/build/libultrasound_native.so",
        root / "native/build/libultrasound_native.dylib",
    )


def native_library_path() -> Path | None:
    return next((path for path in _library_candidates() if path.is_file()), None)


def native_available() -> bool:
    return native_library_path() is not None


@lru_cache(maxsize=4)
def _load_library(path):
    library = ctypes.CDLL(str(path))
    try:
        function = library.plane_wave_das_v2
    except AttributeError as exc:
        raise RuntimeError("rebuild native library: v2 ABI required") from exc
    pointer = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
    function.argtypes = ([pointer]*5 + [ctypes.c_int]*5 + [ctypes.c_double]*4
                         + [ctypes.c_int]*2 + [pointer])
    function.restype = None
    library.native_openmp_enabled.argtypes = []
    library.native_openmp_enabled.restype = ctypes.c_int
    return library


def native_build_info():
    path = native_library_path()
    if path is None:
        raise RuntimeError("native backend is not built; see native/README.md")
    return {"library": str(path), "openmp": bool(_load_library(path).native_openmp_enabled())}


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    if value > np.iinfo(np.int32).max:
        raise ValueError(f"{name} exceeds native integer range")
    return int(value)


def native_plane_wave_delay_and_sum(
    acquisition: UFFAcquisition,
    angle_count: int = 11,
    lateral_stride: int = 2,
    axial_stride: int = 2,
    f_number: float = 1.5,
    dynamic_range_db: float = 60.0,
    analytic: bool = False,
    interpolation: str = "linear",
    angle_batch_size: int = 8,
    threads: int = 8,
) -> PlaneWaveResult:
    """Focus bounded angle batches; double accumulation, no hidden float32 conversion.

    Hilbert and log compression remain SciPy/NumPy. This is a native focusing
    prototype, not a complete C++ acquisition/display stack. No cross-frame cache.
    """
    for name, value in (("angle_count", angle_count), ("lateral_stride", lateral_stride),
                        ("axial_stride", axial_stride), ("angle_batch_size", angle_batch_size),
                        ("threads", threads)):
        _positive_int(value, name)
    if not np.isfinite([f_number, dynamic_range_db]).all() or min(f_number, dynamic_range_db) <= 0:
        raise ValueError("f_number and dynamic_range_db must be finite and positive")
    channel = np.asarray(acquisition.channel_data)
    if channel.ndim != 3 or channel.dtype not in (np.dtype("float32"), np.dtype("float64")):
        raise ValueError("channel_data must be real float32/float64 [angle, element, sample]")
    for size in channel.shape:
        _positive_int(size, "channel dimension")
    order = _validate_delay_interpolation(interpolation, channel.shape[-1])
    if channel.shape[-1] < 2:
        raise ValueError("at least two channel samples are required")
    angles = np.asarray(acquisition.transmit_angles_rad, dtype=float)
    elements = np.asarray(acquisition.element_x_m, dtype=float)
    x = np.asarray(acquisition.x_axis_m, dtype=float)
    z = np.asarray(acquisition.z_axis_m, dtype=float)
    if any(a.ndim != 1 or not a.size or not np.isfinite(a).all()
           for a in (angles, elements, x, z)):
        raise ValueError("geometry arrays must be nonempty finite vectors")
    if angles.size != channel.shape[0] or elements.size != channel.shape[1]:
        raise ValueError("channel dimensions do not match geometry")
    fs, speed, t0 = (acquisition.sampling_frequency_hz, acquisition.sound_speed_m_s,
                     acquisition.initial_time_s)
    if not np.isfinite([fs, speed, t0]).all() or fs <= 0 or speed <= 0:
        raise ValueError("invalid sampling frequency, sound speed or initial time")
    indices = select_transmit_indices(angles, angle_count)
    x = np.ascontiguousarray(x[::lateral_stride])
    z = np.ascontiguousarray(z[::axial_stride])
    _positive_int(x.size, "x size")
    _positive_int(z.size, "z size")
    elements = np.ascontiguousarray(elements)
    path = native_library_path()
    if path is None:
        raise RuntimeError("native backend is not built; see native/README.md")
    function = _load_library(path).plane_wave_das_v2
    output = np.zeros((z.size, x.size), dtype=complex if analytic else float)
    for start in range(0, indices.size, angle_batch_size):
        batch = indices[start:start+angle_batch_size]
        real = np.ascontiguousarray(channel[batch])
        if not np.isfinite(real).all():
            raise ValueError("non-finite RF samples")
        batch_angles = np.ascontiguousarray(angles[batch])

        def focus(data, current_angles=batch_angles):
            result = np.empty((z.size, x.size), dtype=float)
            function(np.ascontiguousarray(data, dtype=float), current_angles, elements, x, z,
                     current_angles.size, elements.size, channel.shape[-1], x.size, z.size,
                     fs, speed, t0, f_number, order, threads, result)
            return result

        focused = focus(real)
        if analytic:
            focused = focused + 1j*focus(hilbert(real, axis=-1).imag)
        output += focused * (batch.size/indices.size)
        del real, focused
    envelope = np.abs(output) if analytic else envelope_detect(output)
    return PlaneWaveResult(output, log_compress(envelope, dynamic_range_db), x, z, indices)
