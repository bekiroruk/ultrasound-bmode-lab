# Optional C++ backend

This directory contains the same conventional plane-wave DAS loop as the NumPy and Numba
implementations, exposed through a small C ABI. It is optional and is not built in CI.

```bash
cmake -S native -B native/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/build --config Release
```

`ultrasound_bmode.native_backend` looks for the resulting shared library under the build tree.
The benchmark records the backend as unavailable when a compiler/library is not present; it does
not substitute an estimated runtime.
