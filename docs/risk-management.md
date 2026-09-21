# Research risk-management record

This file adapts the structure of a medical-device risk register for engineering practice. It is
not an ISO 14971 risk-management file and does not establish device safety or regulatory
compliance.

Qualitative ratings are `low`, `medium`, and `high`. Residual ratings assume the listed controls
are present and verified.

| ID | Hazardous situation / possible harm | Initial risk | Control | Verification | Residual risk |
|---|---|---:|---|---|---:|
| R-001 | A reconstruction is mistaken for a diagnostic image, leading to an unsupported clinical decision. | High | Non-clinical intended-use statement; no diagnosis output; dataset and algorithm limitations displayed. | README/document review. | Medium |
| R-002 | Incorrect sound speed or timing shifts anatomy or phantom targets. | High | UFF metadata is authoritative; timing is tested; position error is measured on a physical phantom. | `DATA-001`, `ALG-001`, phantom JSON. | Medium |
| R-003 | Delay/interpolation defect creates false structures. | High | Independent synthetic impulse fixture; NumPy/Numba agreement; reference correlation and RMSE. | `ALG-001`, `ALG-002`, `PERF-001`. | Medium |
| R-004 | Aggressive adaptive beamforming removes true low-coherence tissue. | High | Adaptive methods are separate named baselines; DAS remains default; all metrics and images are retained. | Adaptive comparison artifact. | Medium |
| R-005 | TGC or despeckling makes an image visually attractive while reducing fidelity. | High | Stage-by-stage ablation against the reference; no automatic replacement of the baseline. | Enhancement metrics JSON. | Medium |
| R-006 | Biased ROI placement inflates a quality metric. | Medium | ROI geometry is stored, overlaid, applied to both images, and accompanied by bootstrap intervals. | ROI tests and overlay. | Low–medium |
| R-007 | Dataset corruption or silent source change invalidates results. | Medium | Immutable Zenodo record, exact size, MD5 verification, raw data excluded from Git. | Downloader rejection path and provenance record. | Low |
| R-008 | Performance optimization changes numerical output. | Medium | Compiled and reference RF outputs are compared at strict tolerance; JIT time is separated. | `PERF-001`, acceleration JSON. | Low |
| R-009 | A dependency or Python update changes results. | Medium | CI on two Python versions, unit tests, machine-readable reference artifacts. | CI and regression review. | Low–medium |
| R-010 | Human-data provenance or license is obscured. | Medium | Public de-identified research source, license/citation file, no raw redistribution. | Provenance documentation review. | Low |

## Open risk work

- Validate on more subjects, probes, frequencies, and vendors.
- Add sound-speed sensitivity and aberration experiments.
- Replace pixel bootstrap with spatial/block or acquisition-level uncertainty where appropriate.
- Define clinical users, intended purpose, safety classification, benefit-risk criteria, and
  post-market controls before any device-oriented interpretation.
