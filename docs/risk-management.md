# Research risk-management record

This file adapts the structure of a medical-device risk register for engineering practice. It is
not an ISO 14971 risk-management file and does not establish device safety or regulatory
compliance.

Qualitative ratings are `low`, `medium`, and `high`. Residual ratings assume the listed controls
are present and verified.

| ID | Hazardous situation / possible harm | Initial risk | Control | Verification | Residual risk |
|---|---|---:|---|---|---:|
| R-001 | A reconstruction is mistaken for a diagnostic image, leading to an unsupported clinical decision. | High | Non-clinical intended-use statement; no diagnosis output; dataset and algorithm limitations displayed. | README/document review. | Medium |
| R-002 | Incorrect sound speed or timing shifts anatomy or phantom targets. | High | UFF metadata is authoritative; timing is tested; fixed sound-speed sensitivity is reported without retuning on approximate target coordinates. | `DATA-001`, `ALG-001`, `MET-008`, phantom JSON. | Medium |
| R-003 | Delay/interpolation defect creates false structures. | High | Independent synthetic fixtures; linear/cubic NumPy/Numba agreement; measured phantom comparison; reference correlation and RMSE. | `ALG-001`, `ALG-002`, `ALG-017`, `PERF-001`. | Medium |
| R-004 | Aggressive adaptive beamforming removes true low-coherence tissue. | High | Adaptive methods are separate named baselines; DAS remains default; all metrics and images are retained. | Adaptive comparison artifact. | Medium |
| R-005 | TGC or despeckling makes an image visually attractive while reducing fidelity. | High | Stage-by-stage ablation against the reference; no automatic replacement of the baseline. | Enhancement metrics JSON. | Medium |
| R-006 | Biased ROI placement inflates a quality metric. | Medium | ROI geometry is stored, overlaid, applied to both images, and accompanied by bootstrap intervals. | ROI tests and overlay. | Low–medium |
| R-007 | Dataset corruption or silent source change invalidates results. | Medium | Immutable Zenodo record, exact size, MD5 verification, raw data excluded from Git. | Downloader rejection path and provenance record. | Low |
| R-008 | Performance optimization changes numerical output. | Medium | Compiled and reference RF outputs are compared at strict tolerance; JIT time is separated. | `PERF-001`, acceleration JSON. | Low |
| R-009 | A dependency or Python update changes results. | Medium | CI on two Python versions, unit tests, machine-readable reference artifacts. | CI and regression review. | Low–medium |
| R-010 | Human-data provenance or license is obscured. | Medium | Public de-identified research source, license/citation file, no raw redistribution. | Provenance documentation review. | Low |
| R-011 | A stale analytic cache is paired with different or mutated RF data, producing invalid reconstruction. | Medium | Cache is bound to the exact source array instance; shape/dtype/mode are checked; cache quadrature is read-only; source immutability is documented. | `ALG-016` cache misuse and parity tests. | Low–medium |

## Open risk work

- v0.15's bin-free point metric can understate multi-crossing gCNR. The
  mathematically conservative independence-aware interval is uninformative
  (`[0,1]`) for the small synthetic source-cell sample, while applying its
  IID guarantee to dependent image pixels is invalid. Do not promote it to
  measured-image inference without a separately validated dependence model.
- v0.14 Rayleigh-model testing reduced estimator bias in its own generating model,
  but aligned correlated tiles reached only 89% and non-Rayleigh data 45% on the
  final independent seed. Do not substitute its intervals for measured-image
  inference without separately validating the distribution and correlation model.
- Validate on more subjects, probes, frequencies, and vendors.
- Extend the completed homogeneous sound-speed sweep with calibration and aberration experiments.
- Calibrate the conditional spatial-tile intervals; separate ROI/tile-origin sensitivity has
  been measured on two acquisitions. The v0.13 known-truth audit found undercoverage,
  including 0/200 gCNR coverage in the correlated-tile scenario; intervals remain
  exploratory, not calibrated 95% confidence. Joint interactions, observer selection and
  acquisition-level/between-subject uncertainty remain unmeasured.
- Define clinical users, intended purpose, safety classification, benefit-risk criteria, and
  post-market controls before any device-oriented interpretation.

## v0.13 controls

- SWE L7 is not labeled as patient data; specimen and acquisition rate are unknown.
  Offline timing cannot establish a live-device deadline.
- Python validates geometry, dimensions, dtype and finite selected samples before ABI entry;
  C++ checks sample-position range before integer conversion. Tests cover cubic stencil edges.
- Sampled RSS cannot prove leak freedom. No C++/GPU speedup is inferred from language or
  hardware presence; the measured C++ prototype is slower than Numba.
- Completing a coverage audit is not passing a calibration criterion.
