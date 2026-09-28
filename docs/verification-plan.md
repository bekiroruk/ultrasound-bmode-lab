# Verification and traceability plan

This lightweight plan demonstrates requirements-driven algorithm development. It is not a claim of IEC 62304, ISO 13485, or regulatory compliance.

## Intended use and boundaries

The software reconstructs educational B-mode images from synthetic data and public,
de-identified research acquisitions. It is not intended to control hardware, support diagnosis,
make a clinical claim, or process data in a care-delivery workflow.

## Traceability matrix

| ID | Software requirement | Verification evidence | Acceptance criterion |
|---|---|---|---|
| ALG-001 | Reconstruct a point reflector using physical propagation delays. | `test_delay_and_sum_focuses_impulse_on_expected_depth` | Peak error is at most two reconstruction samples. |
| ALG-002 | Reconstruct finite output with valid fractional sample support. | `test_coarse_real_reconstruction_is_finite`, `DelayInterpolationTests` | Measured output is finite; unsupported sample positions are rejected. |
| ALG-003 | Apply depth-dependent receive aperture and reject invalid F-number. | Beamformer validation and aperture study review | Aperture weights remain finite; positive F-number required. |
| ALG-004 | Compound reproducible subsets selected by physical steering angle. | `AngleSelectionTests` | Single angle selects 0°; multi-angle subsets include published extremes. |
| ALG-005 | Bound the displayed image to the configured dynamic range. | `test_log_compression_range_and_peak` | Peak is 0 dB; floor is the configured negative limit. |
| ALG-006 | Provide named adaptive beamforming baselines. | `AdaptiveBeamformingTests` | Coherent/incoherent, DMAS identity and finite MVDR fixtures pass. |
| ALG-007 | Keep preprocessing and display stages separately testable. | `ProcessingTests` and enhancement report | RF tone, common-mode, TGC, compression and diffusion fixtures pass; stage effects recorded. |
| DATA-001 | Preserve the published UFF acquisition dimensions and metadata. | `test_uff_dimensions_and_metadata` | 75 × 128 × 1,536 RF tensor, 20.832 MHz sampling, and 609 × 387 reference grid. |
| DATA-002 | Bind USTB retrieval to published bytes and checksum. | Downloader implementation review and local data provenance | Published size/MD5 retained; mismatch rejection requires a dedicated negative-path automated test before formal release. |
| MET-001 | Similarity metrics shall recover identity and reject incompatible shapes. | `MetricTests` | Correlation/SSIM are one, RMSE zero, PSNR infinite for identical images. |
| MET-002 | Physical point-target measurement shall recover analytical Gaussian FWHM. | `test_gaussian_point_target_fwhm` | Axial and lateral error are each below 0.02 mm. |
| PERF-001 | Compiled and reference DAS shall be numerically equivalent. | `test_numba_kernel_matches_numpy_on_coarse_real_grid` | RF agrees at `rtol=1e-5`, `atol=1e-7`. |
| MET-003 | Translation registration and uncertainty calculation shall be reproducible. | `RoiAnalysisTests` | Integer shift is exact and fixed-seed bootstrap output repeats. |
| DATA-003 | EPFL RF dimensions shall agree with its settings and global time axis. | `EpflLoaderTests` | Mismatched angle, element, sample, or sampling metadata is rejected. |
| DATA-004 | Selective EPFL retrieval shall retain integrity checks. | Downloader implementation review and EPFL provenance | Member size, ZIP CRC32 and SHA-256 retained; negative-path automated download tests remain future work. |
| ALG-012 | Channel-analytic CPWC shall recover a known envelope on a coarse output grid. | `test_recovers_known_envelope_on_undersampled_depth_grid` | Gaussian amplitude absolute error ≤ 1e-9 at the analytical sample coordinates. |
| ALG-013 | Analytic RF at shared coordinates shall not depend on output-grid subsampling. | `test_complex_rf_is_invariant_to_output_grid_subsampling` | Complex output agrees at `rtol=1e-12`, `atol=1e-12`. |
| PERF-003 | Analytic Numba and NumPy shall agree without external datasets. | `test_numba_matches_numpy_with_delays_angles_and_invalid_samples` | Real/analytic RF agree at `rtol=1e-5`, `atol=1e-7`; displayed dB at `atol=1e-4`; 1/3/5 physical-angle subsets. |
| DATA-005 | The comparison report shall retain exact data/configuration provenance. | `QualityReportTests` and `artifacts/analytic_quality/quality_metrics.json` | Offline test produces parseable JSON and a figure; measured report includes SHA-256, geometry sampling and selected angles. |
| MET-005 | FWHM shall accept boundary-bracketed crossings and reject truncated profiles. | Two edge tests in `PhantomMeasurementTests` | Triangular profile width equals 1; unbracketed peak returns NaN internally and null in report. |
| MET-006 | Analytic phantom reports shall retain both modes, per-target validity and same-grid references. | `test_phantom_report_retains_all_points_modes_and_matched_reference` | Ten records, seven targets per resolution record, reference metrics equal direct same-grid measurement. |
| MET-007 | Grid consistency shall compare linear envelopes without hiding scale error. | `AnalyticValidationTests` | Factor-two amplitude error remains visible; misaligned coordinates are rejected. |
| DATA-006 | External reports shall distinguish within-method stability from independent accuracy. | `test_external_report_keeps_same_mode_references_separate` | Both mode records use own full-angle reference; reference limitation and provenance retained. |
| ALG-014 | Aperture selection shall honor both cysts, axial-width and valid-target guardrails. | `ApertureSelectionTests` | Reject nonfinite or missing measurements, insufficient targets and limit violations; exclude fine-grid/75-angle records from selection. |
| PERF-004 | Warmup, timing and memory sampling shall be distinct passes. | `RuntimeProtocolTests` | Two timed repeats entail four total calls; warmup excluded from median; RSS peak >= baseline; invalid settings fail. |
| PERF-005 | Measured profiles shall retain full-array backend parity checks. | `artifacts/runtime_profile/metrics.json` | NumPy/Numba 11-angle real and complex RF at `rtol=1e-5`, `atol=1e-7`; B-mode at `atol=1e-4` dB. |
| ALG-015 | Angle batching shall weight partial batches correctly before envelope extraction. | `AngleBatchingTests` | RF agrees with NumPy at `rtol=1e-5`, `atol=1e-7` over real/analytic modes, 1/5/7 angles and six batch choices; input unchanged, invalid batch sizes rejected. |
| DATA-007 | Frozen transfer shall preserve geometry, reference semantics and both F-numbers. | `TransferParityTests` | Misaligned coordinates, reordered angles or altered outputs fail; report retains F/1.7 and F/0.8 with reference type. |
| PERF-006 | Batched profiles shall compare only like-for-like configurations. | `BatchProfileReportTests` and measured batch report | Six sequential configurations use correct same-F-number baseline; full-array RF/B-mode agreement required before publishing measurements. |
| ALG-016 | Reusable analytic cache shall preserve output and reject invalid reuse. | `test_analytic_cache.py` | Batched preparation matches SciPy Hilbert; cached/uncached output agrees; wrong source, shape, dtype, type and mode are rejected. |
| PERF-007 | Cache performance evidence shall separate preparation, repeated timing and memory. | `CacheProfileReportTests` and `artifacts/cache_profile/metrics.json` | Four fresh-process cases retain preparation time/bytes, raw repeats, RSS, break-even calculation and full-array parity. |
| ALG-017 | Cubic channel-delay interpolation shall reduce controlled fractional-delay error and preserve backend parity. | `DelayInterpolationTests` | Cubic sinusoid RMSE is less than 20% of linear; NumPy/Numba real/analytic outputs agree; invalid method/support fails. |
| MET-008 | Measured interpolation/sound-speed study shall retain scope and non-selection limits. | `InterpolationStudyReportTests` and `artifacts/interpolation_study/metrics.json` | Both methods at 11/full angles and all five fixed speeds are present; defaults explicitly remain unchanged. |
| DATA-008 | Frozen cubic transfer shall separate change from reference quality and preserve geometry. | `InterpolationTransferTests` and `artifacts/interpolation_transfer/metrics.json` | Ten measured cubic cache/batch comparisons pass; unavailable reference scores are null; axes, angles and source/settings hashes retained. |
| PERF-008 | Matched interpolation profiling shall reverse process order and require same-method repeat parity. | `InterpolationProfileTests` and `artifacts/interpolation_profile/metrics.json` | Eight fresh processes, ten warm calls/configuration; geometry/output drift rejected; four repeat comparisons pass; raw timings and separate RSS retained. |

## Reproducibility controls

MET-010 is verified by `RoiSensitivityTests`, shifted-origin `SpatialRoiTests` and
`artifacts/roi_sensitivity/metrics.json`. Origin validation rejects negative, fractional,
boolean, oversized and malformed offsets. All four tested origins retain the same pixel
counts, point estimates and paired identity. Report tests verify ten one-factor conditions,
both reference-based/manual selection policies, exact geometry and EPFL settings hashes.

MET-009 is verified by `SpatialRoiTests`, `AnalyticRoiReportTests` and
`artifacts/analytic_roi/metrics.json`. Tests require deterministic paired identity,
unchanged point estimates across block sizes, intact tile resampling, a wider contrast
range on a tile-correlated fixture, finite nonnegative envelopes and valid ROI geometry.
The measured study uses one frozen reference ROI, six reconstructions, four block sizes
and 500 accepted paired draws per size. The 16×16 case rejected four unsupported draws;
this conditioning is recorded rather than hidden. No coverage calibration is claimed.

- Simulation and electronic noise use explicit, independently derived seeds.
- Calculations use SI units; display conversions occur only at visualization boundaries.
- Default parameters are centralized in the immutable `ImagingConfig` object.
- The JSON metric artifact makes regression thresholds machine-readable.
- CI runs the same test suite on two supported Python versions, with Numba installed so
  the dataset-independent accelerated parity test actually executes. Installed-data checks
  skip when large external acquisitions are absent; local validation runs them as well.

## Main technical risks

| Risk | Existing control | Further work before real-data use |
|---|---|---|
| Incorrect propagation-speed assumption | Metadata speed, synthetic focus test and fixed homogeneous speed sweep | Add calibration dataset and aberration study; separate geometry shifts from defocus. |
| Delay/interpolation error | Linear/cubic parity, analytical sinusoid error and measured phantom comparison | Add higher-order analytical point-spread-function and bandwidth sweeps. |
| Limited generalization | Four in-vivo carotid acquisitions, two explicit EPFL volunteers, three probes, and physical phantom cross-platform evidence | Add more subjects, disease states, operators, laboratories, and multi-vendor human acquisitions. |
| ROI selection bias | Stored/overlaid geometry, common ROI, registration, and bootstrap intervals | Add blinded multi-observer ROIs and spatial uncertainty. |
| Numerical or dependency regression | Unit tests and versioned CI environment | Lock validated dependency versions for a formal release. |

## Reference test procedure

1. Create a clean Python environment and install the project with development dependencies.
2. Run `python -m unittest discover -s tests -v` and retain the console record.
3. Download each controlled USTB item with `scripts/download_picmus.py --dataset <alias>` and
   the selected EPFL items with `scripts/download_epfl.py --sample all`.
4. Run the synthetic, angle benchmark, adaptive, phantom, enhancement, acceleration, ROI, external,
   `ultrasound-quality`, `ultrasound-validate-analytic`, `ultrasound-aperture-study` and
   `ultrasound-profile`, `ultrasound-aperture-transfer`, `ultrasound-batch-profile` and
   `ultrasound-cache-profile`, `ultrasound-interpolation-study`,
   `ultrasound-interpolation-transfer` and `ultrasound-interpolation-profile` commands
   documented in the README. Run profiling after other compute
   experiments finish; do not benchmark backends concurrently.
   Keep legacy and analytic results separate. Analytic fixed-ROI/FWHM measurements are
   available; spatial uncertainty and independent aperture-candidate validation remain future work.
5. Confirm that every expected PNG/JSON/CSV artifact is produced and contains finite values.
6. Inspect point targets, cyst ROIs, carotid ROI, and depth behavior for gross artifacts.
7. Compare metric JSON values with the approved baseline using stated tolerances.
8. Record the commit SHA, dependency freeze, dataset checksums, host, and command lines.

## v0.10 local execution record

- Python 3.12 with installed measured datasets and Numba: **84 tests passed**, including
  113 pytest subtests. Cubic backend acceptance uses RF `rtol=1e-5, atol=1e-7` and
  B-mode `rtol=0, atol=1e-4` dB.
- Five transfer acquisitions, 11/full angles: all ten cached/batched cubic comparisons passed.
- Matched profile: two reversed process orders, five timed repeats per worker, eight Numba
  threads; all four same-method repeat comparisons passed.
- Inspect the JSON artifacts for host, dependencies, checksums, raw repeats and limitations.
  Clinical validation, sustained frame streaming and device-hardware deployment remain excluded.

## v0.11 local execution record

The extended suite contains 93 tests. Measured ROI artifacts preserve the legacy study and
record new analytic/paired-spatial results separately. Block sizes in physical units and
each region's occupied tile counts are retained; the fixed-origin, fixed-ROI single-acquisition
intervals must not be interpreted as clinical or population confidence intervals.

## v0.12 local execution record

The extended suite contains 99 tests. Twenty measured conditions use 500 accepted draws each;
all have at least nine target tiles and no rejected resamples. PICMUS baseline paired
contrast/CNR/gCNR point estimates and intervals match the v0.11 8×8 study exactly. Three of
four gCNR point differences change sign across ROI choices; all 16 baseline/origin gCNR
intervals contain zero. This is sensitivity evidence, not calibrated inference or equivalence.
