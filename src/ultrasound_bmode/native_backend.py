"""ctypes bridge for the optional C++ DAS reference backend."""

from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np

from .processing import envelope_detect, log_compress
from .real_data import PlaneWaveResult, UFFAcquisition, select_transmit_indices


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


def native_plane_wave_delay_and_sum(
    acquisition: UFFAcquisition,
    angle_count: int = 11,
    lateral_stride: int = 2,
    axial_stride: int = 2,
    f_number: float = 1.5,
    dynamic_range_db: float = 60.0,
) -> PlaneWaveResult:
    path = native_library_path()
    if path is None:
        raise RuntimeError("native backend is not built; see native/README.md")
    channel = np.ascontiguousarray(acquisition.channel_data, dtype=np.float32)
    angles = np.ascontiguousarray(acquisition.transmit_angles_rad, dtype=np.float64)
    indices = np.ascontiguousarray(select_transmit_indices(angles, angle_count), dtype=np.int32)
    elements = np.ascontiguousarray(acquisition.element_x_m, dtype=np.float64)
    x_axis = np.ascontiguousarray(acquisition.x_axis_m[::lateral_stride], dtype=np.float64)
    z_axis = np.ascontiguousarray(acquisition.z_axis_m[::axial_stride], dtype=np.float64)
    output = np.zeros((z_axis.size, x_axis.size), dtype=np.float64)

    library = ctypes.CDLL(str(path))
    function = library.plane_wave_das
    float_pointer = np.ctypeslib.ndpointer(dtype=np.float32, flags="C_CONTIGUOUS")
    double_pointer = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
    int_pointer = np.ctypeslib.ndpointer(dtype=np.int32, flags="C_CONTIGUOUS")
    function.argtypes = [
        float_pointer,
        double_pointer,
        int_pointer,
        double_pointer,
        double_pointer,
        double_pointer,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        double_pointer,
    ]
    function.restype = None
    function(
        channel,
        angles,
        indices,
        elements,
        x_axis,
        z_axis,
        indices.size,
        channel.shape[0],
        channel.shape[1],
        channel.shape[2],
        x_axis.size,
        z_axis.size,
        acquisition.sampling_frequency_hz,
        acquisition.sound_speed_m_s,
        acquisition.initial_time_s,
        f_number,
        output,
    )
    bmode = log_compress(envelope_detect(output), dynamic_range_db)
    return PlaneWaveResult(output, bmode, x_axis, z_axis, indices)
