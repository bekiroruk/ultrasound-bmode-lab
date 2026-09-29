# Optional C++ backend

This optional C++17/OpenMP focusing prototype supports real and channel-analytic RF,
linear and Catmull-Rom cubic interpolation, and bounded angle batches. The v2 C ABI
accepts contiguous float64 batches; the Python wrapper validates shapes, finite
metadata and selected samples before entering native code. Hilbert preprocessing
and log compression remain Python/SciPy: this is not a standalone C++ imaging system.
CI builds the library before testing it on Python 3.10/3.12.

```bash
cmake -S native -B native/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/build --config Release
```

`ultrasound_bmode.native_backend` looks for the resulting shared library under the build tree.
The benchmark records the backend as unavailable when a compiler/library is not present; it does
not substitute an estimated runtime.

Windows requires an installed C++ toolchain (tested with Visual Studio 2022 / MSVC
19.44.35228, OpenMP 2.0). Run the build with no Python process holding the DLL open.
Linux uses a C++17 compiler and CMake; OpenMP is optional and its availability is
recorded. No `-ffast-math` is used in the v2 build.

Python usage:

```python
from ultrasound_bmode.native_backend import native_plane_wave_delay_and_sum
result = native_plane_wave_delay_and_sum(
    acquisition, angle_count=11, analytic=True, interpolation="cubic",
    angle_batch_size=8, threads=8,
)
```

Measured acceptance: RF `rtol=1e-5, atol=1e-7`; B-mode `rtol=0, atol=1e-4` dB.
The wrapper preserves float32/float64 input precision; the kernel accumulates in double.
An old DLL without the v2 ABI produces a rebuild error. Library discovery alone does
not guarantee ABI compatibility.

See [matched runtime / memory and equivalence evidence](../artifacts/native_profile/README.md).
The current C++ loop is slower than Numba on the measured host; portability and numerical
correctness are demonstrated, not a speedup or deployment-ready real-time platform.
