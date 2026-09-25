# Algorithm design description

## Architecture

```text
verified UFF
  ├─ metadata + RF loader
  ├─ optional RF preprocessing
  ├─ transmit/receive delay model
  ├─ fractional interpolation + dynamic aperture
  ├─ DAS / CF / PCF / DMAS / MVDR
  ├─ coherent plane-wave compounding
  ├─ envelope + gain + display mapping
  └─ reference, phantom, ROI, uncertainty, and runtime reports
```

The conventional implementation favors readability and keeps all dimensions visible. The
Numba backend implements the same delay, interpolation, aperture, and normalization equations
in a parallel compiled loop. Tests compare both backends directly.

## Propagation model

For pixel `(x, z)`, receive element position `x_e`, plane-wave steering angle `theta`, and
assumed sound speed `c`:

```text
t = [x sin(theta) + z cos(theta) + sqrt((x - x_e)^2 + z^2)] / c
```

The stored initial acquisition time is subtracted before conversion to a fractional sample
index. Values outside the recorded sample interval do not contribute.

## Receive aperture and combination

The half-aperture is `z / (2 F#)`. Elements inside it receive a cosine weight. Conventional DAS
normalizes the weighted sum by the weight sum. Adaptive methods reuse the same delayed aperture:

- CF weights DAS by coherent energy divided by total aperture energy.
- PCF weights analytic DAS by the squared circular phase-resultant length.
- DMAS uses signed square-root pair products, evaluated with an algebraic pair-sum identity.
- MVDR estimates a loaded covariance matrix from overlapping receive subarrays and applies a
  distortionless Capon weight.

These are research baselines. Their output amplitudes are not interchangeable, so comparisons
use normalized display images and method-specific phantom metrics.

## Processing and evaluation

The legacy default display path is output-depth Hilbert envelope followed by 60 dB log
compression. The v0.4 `analytic=True` option instead applies
[`scipy.signal.hilbert`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.hilbert.html)
along the original channel sample axis, before fractional-delay interpolation. Complex
beamformed signals are coherently compounded before taking magnitude. This is analytic RF,
not baseband IQ demodulation, and does not require an assumed carrier frequency.

The motivation is sampling: for an on-axis pulse-echo path, `dt = 2 dz / c`, so the equivalent
output-grid RF Nyquist limit is `c / (4 dz)`. A coarse image grid need not support the RF
carrier even when channel acquisition satisfies Nyquist. Channel-analytic processing avoids
performing Hilbert on this undersampled grid. It does not correct insufficient acquisition
sampling, channel boundaries, bandwidth limitations or interpolation error. Complex analytic
RF samples themselves may still be spatially undersampled; they must not be interpreted as a
new adequately sampled RF time series.

NumPy focuses complex samples directly. Numba runs the same real kernel on real and quadrature
channels and combines the results. CUDA and native C++ are not changed. Signed real DMAS
rejects the analytic flag. Existing CF/PCF/MVDR already operate on analytic channels.

`ultrasound-quality` holds output coordinates, F-number, angle indices and display range fixed
and compares each path against the embedded UFF image sampled on that same grid. Peak
normalization is independent per image; the reference is normalized before subsampling.
This experiment does not change or reuse historical phantom FWHM/runtime claims.

The v0.5 `ultrasound-validate-analytic` experiment separately evaluates fixed-ROI linear
envelope contrast and FWHM, using F-number 1.7 and the same stride-2 grid for reconstruction
and embedded reference. Widths subtract a local 20th-percentile baseline and interpolate
half-amplitude crossings. Crossings bracketed by edge samples are accepted; profiles still
above half maximum at the boundary are truncated and reported as null, with valid counts.
Both improved and worsened metrics are retained.

External EPFL/Alpinion cases have no independent image reference. Each mode's 11-angle
reconstruction is compared to that same mode's full-angle reconstruction; these are
within-method stability scores, not a comparison of accuracy across methods. A separate
grid test compares linear envelopes on shared coordinates, normalized by the shared fine-grid
peak (never per-image renormalization). Analytic invariance is a numerical property of the
implementation, not evidence of anatomical correctness. Data and EPFL settings checksums,
geometry and selected angle indices are retained with each report.

Optional stages
are evaluated as an ablation: common-mode rejection, data-driven RF band-pass, automatic TGC,
adaptive range, and anisotropic diffusion. A stage is retained in the report even when a metric
worsens; this prevents selective reporting.

Real in-vivo quality uses the UFF 75-angle image as a reconstruction reference, not as anatomical
ground truth. Physical CIRS phantom measurements provide controlled cyst and point-target
evidence. Pixel bootstrap intervals quantify sampling variability inside the selected ROI but do
not model spatial correlation or inter-subject uncertainty.

## Key design decisions and limitations

### Exploratory aperture selection and performance protocol (v0.6)

The receive F-number sweep changes only aperture width; propagation, interpolation,
compounding and envelope stages stay fixed. Candidate selection minimizes median lateral
FWHM at 11 angles/stride 2 subject to valid widths for all seven targets, axial FWHM no more
than 5% above F/1.7, and each cyst gCNR no more than 0.02 below F/1.7. Repeats at 75 angles
and stride 1 reuse the same acquisitions. Selection is exploratory, does not change defaults,
and cannot establish an optimum beyond the sampled parameter range or clinical utility.

Performance profiling fixes F/1.5 on the carotid acquisition, independently of aperture
selection. Each backend/mode/count uses a fresh sequential subprocess. One full warmup
includes any cache/JIT overhead; three subsequent full calls measure reconstruction time.
An additional call samples process RSS at a requested 2 ms interval. Timed calls do not run
the memory sampler. Working-set baselines include resident data and retained allocator
buffers, so incremental RSS is not total temporary allocation. Reports retain raw repeats,
host/dependency information, data hash and full-array 11-angle backend agreement.

- Constant 1,540 m/s sound speed can cause target-position and focus errors in heterogeneous
  tissue.
- Linear delay interpolation is transparent but less accurate than higher-order interpolation.
- The CPU reference prioritizes clarity; Numba provides performance without changing equations.
- The current MVDR covariance estimate uses spatial smoothing and diagonal loading; it is not a
  tuned clinical implementation.
- Automatic enhancement is never substituted silently for the baseline image.
