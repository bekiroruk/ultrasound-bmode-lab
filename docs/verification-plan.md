# Verification and traceability plan

This lightweight plan demonstrates requirements-driven algorithm development. It is not a claim of IEC 62304, ISO 13485, or regulatory compliance.

## Intended use and boundaries

The software reconstructs educational B-mode images from synthetic data and public,
de-identified research acquisitions. It is not intended to control hardware, support diagnosis,
make a clinical claim, or process data in a care-delivery workflow.

## Traceability matrix

| ID | Software requirement | Verification evidence | Acceptance criterion |
|---|---|---|---|
| ALG-001 | Reject sampling configurations below the Nyquist limit. | `test_nyquist_validation` | Invalid configuration raises a clear error. |
| ALG-002 | Reconstruct a point reflector at its expected axial position. | `test_delay_and_sum_focuses_impulse_on_expected_depth` | Peak error is at most two reconstruction samples. |
| ALG-003 | Extract an RF amplitude envelope using an analytic signal. | `test_envelope_of_sinusoid_is_nearly_constant` | Interior sinusoid envelope is `1 ± 0.03`. |
| ALG-004 | Increase compensation gain monotonically with depth. | `test_tgc_increases_with_depth` | Gain strictly increases for positive attenuation. |
| ALG-005 | Bound the displayed image to the configured dynamic range. | `test_log_compression_range_and_peak` | Peak is 0 dB; floor is the configured negative limit. |
| ALG-006 | Quantify a low-echo cyst relative to its background. | `test_cyst_metrics_detect_low_echo_region` | Contrast is negative, CNR > 1, and gCNR is in `[0, 1]` for the controlled fixture. |
| ALG-007 | Reject malformed channel-data dimensions. | `test_beamformer_rejects_wrong_shape` | Reconstruction fails before numerical processing. |
| DATA-001 | Preserve the published UFF acquisition dimensions and metadata. | `test_uff_dimensions_and_metadata` | 75 × 128 × 1,536 RF tensor, 20.832 MHz sampling, and 609 × 387 reference grid. |
| ALG-008 | Produce finite B-mode output from measured RF channel data. | `test_coarse_real_reconstruction_is_finite` | Every reconstructed dB sample is finite. |
| DATA-002 | Use reproducible steering-angle subsets. | `AngleSelectionTests` | Single-angle selects 0°; multi-angle selection includes both published extremes. |
| ALG-009 | Adaptive aperture methods shall distinguish coherent and incoherent fixtures. | `AdaptiveBeamformingTests` | CF/PCF are one for coherent samples and near zero for uniformly distributed phase. |
| ALG-010 | DMAS and MVDR implementations shall return finite, normalized baseline outputs. | `AdaptiveBeamformingTests` | Pair identity matches the analytical fixture; MVDR output is finite. |
| MET-001 | Similarity metrics shall recover identity and reject incompatible shapes. | `MetricTests` | Correlation/SSIM are one, RMSE zero, PSNR infinite for identical images. |
| MET-002 | Physical point-target measurement shall recover analytical Gaussian FWHM. | `test_gaussian_point_target_fwhm` | Axial and lateral error are each below 0.02 mm. |
| ALG-011 | RF preprocessing and optional display stages shall be deterministic and finite. | `ProcessingTests` | Carrier, common-mode, automatic TGC, compression, and diffusion fixtures pass. |
| PERF-001 | Compiled and reference DAS shall be numerically equivalent. | `test_numba_kernel_matches_numpy_on_coarse_real_grid` | RF agrees at `rtol=1e-5`, `atol=1e-7`. |
| MET-003 | Translation registration and uncertainty calculation shall be reproducible. | `RoiAnalysisTests` | Integer shift is exact and fixed-seed bootstrap output repeats. |

## Reproducibility controls

- Simulation and electronic noise use explicit, independently derived seeds.
- Calculations use SI units; display conversions occur only at visualization boundaries.
- Default parameters are centralized in the immutable `ImagingConfig` object.
- The JSON metric artifact makes regression thresholds machine-readable.
- CI runs the same test suite on two supported Python versions.

## Main technical risks

| Risk | Existing control | Further work before real-data use |
|---|---|---|
| Incorrect propagation-speed assumption | One explicit configuration value; synthetic focus test | Add speed-of-sound sensitivity study and calibration dataset. |
| Delay/interpolation error | Fractional linear interpolation and axial tolerance test | Compare with higher-order interpolation and an analytical point-spread function. |
| Misleading simulated image quality | Real in-vivo and physical CIRS phantom RF evidence plus intended-use disclaimer | Add independent vendors, probes, subjects, and laboratories. |
| ROI selection bias | Stored/overlaid geometry, common ROI, registration, and bootstrap intervals | Add blinded multi-observer ROIs and spatial uncertainty. |
| Numerical or dependency regression | Unit tests and versioned CI environment | Lock validated dependency versions for a formal release. |

## Reference test procedure

1. Create a clean Python environment and install the project with development dependencies.
2. Run `python -m unittest discover -s tests -v` and retain the console record.
3. Download each controlled data item with `scripts/download_picmus.py --dataset <alias>`.
4. Run the synthetic, angle benchmark, adaptive, phantom, enhancement, acceleration, and ROI
   commands documented in the README.
5. Confirm that every expected PNG/JSON/CSV artifact is produced and contains finite values.
6. Inspect point targets, cyst ROIs, carotid ROI, and depth behavior for gross artifacts.
7. Compare metric JSON values with the approved baseline using stated tolerances.
8. Record the commit SHA, dependency freeze, dataset checksums, host, and command lines.
