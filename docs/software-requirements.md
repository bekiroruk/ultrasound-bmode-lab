# Software requirements specification

Status: research baseline, revision 5 (frozen aperture transfer and bounded angle batches)

This specification defines verifiable behavior for the ultrasound B-mode laboratory. The
software is educational/research software and is not intended for diagnosis, treatment,
patient monitoring, or control of an ultrasound scanner.

## Inputs and outputs

Inputs are UFF/HDF5 and EPFL NPZ RF channel data, embedded or separately published acquisition
metadata, and explicit command-line parameters. Outputs are reconstructed RF/IQ arrays,
normalized B-mode images, numerical metric records, and provenance reports. Raw human or phantom
channel files remain outside Git.

## Functional requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| DATA-001 | The loader shall preserve transmit, receive, sample, scan-axis, timing, and sound-speed metadata from supported PICMUS UFF files. | Loaded dimensions and published metadata match the installed files. |
| DATA-002 | Dataset downloads shall be bound to an immutable source record by exact byte size and MD5. | A mismatched existing or downloaded file is rejected. |
| DATA-003 | The EPFL adapter shall verify RF dimensions against steering, probe, and time-axis settings. | Inconsistent angle, element, sample, or sampling metadata is rejected. |
| DATA-004 | Large EPFL archives shall support selective, integrity-checked member retrieval. | The selected member passes byte-size, ZIP CRC32, and recorded SHA-256 checks. |
| ALG-001 | The beamformer shall calculate plane-wave transmit and element-dependent receive propagation time in SI units. | A controlled impulse focuses within two axial samples. |
| ALG-002 | Fractional sample positions shall use linear interpolation and reject out-of-range samples. | Coarse measured-data output is finite and shape-correct. |
| ALG-003 | Receive aperture shall vary with depth and use bounded cosine apodization. | Invalid F-number is rejected; aperture weights remain finite. |
| ALG-004 | The system shall coherently compound reproducible subsets of the available transmissions. | Selection follows physical angle values and includes published steering extremes where applicable. |
| ALG-005 | The display chain shall support analytic-envelope detection and bounded log compression. | Peak is 0 dB and floor equals the selected range. |
| ALG-006 | The research comparison shall provide DAS, CF, PCF, DMAS, and spatially smoothed MVDR baselines. | Coherent and incoherent aperture fixtures satisfy method-specific tests. |
| ALG-007 | Optional preprocessing shall provide RF band-pass, common-mode suppression, automatic TGC, adaptive range, and edge-preserving diffusion as independently reportable stages. | Each stage is finite and its effect is recorded separately. |
| MET-001 | Reference comparison shall report correlation, RMSE, SSIM, and PSNR on aligned grids. | Identical image fixture reports correlation/SSIM 1 and RMSE 0. |
| MET-002 | Physical phantom analysis shall report contrast, CNR, gCNR, speckle SNR, axial FWHM, lateral FWHM, and position error. | Gaussian PSF fixture recovers analytical FWHM within 0.02 mm. |
| MET-003 | Carotid ROI analysis shall report registration, lumen contrast, CNR, gCNR, wall sharpness, and 95% uncertainty intervals. | Known integer translation is recovered exactly; bootstrap is reproducible for a fixed seed. |
| MET-004 | External validation shall retain per-acquisition reference type, subject scope, platform, probe, and anatomy. | JSON and CSV records expose all fields without conflating embedded and same-acquisition references. |
| PERF-001 | A compiled CPU backend shall preserve conventional DAS output within numerical tolerance. | Numba and NumPy RF arrays agree at `rtol=1e-5`, `atol=1e-7`. |
| PERF-002 | Performance reports shall separate one-time compilation from steady-state runtime. | JSON contains compilation time, backend runtime, speedup, and numerical agreement. |
| ALG-012 | Opt-in channel-analytic CPWC shall preserve a known Gaussian RF envelope on an undersampled output grid. | Absolute amplitude error ≤ 1e-9 at exact sample coordinates. |
| ALG-013 | Analytic reconstruction values shall be invariant to output-grid subsampling at common coordinates. | Complex output agrees at `rtol=1e-12`, `atol=1e-12`. |
| PERF-003 | Analytic Numba shall agree with NumPy on dataset-independent multichannel fixtures. | Complex RF agrees at `rtol=1e-5`, `atol=1e-7`; B-mode agrees at `atol=1e-4` dB. |
| DATA-005 | Analytic comparison reports shall identify input files, selected angles and display settings. | Strict JSON includes SHA-256, sampling, shape, F-number, stride, reference policy and per-case before/after metrics. |
| MET-005 | FWHM shall distinguish bracketed edge crossings from truncated profiles. | Bracketed half-amplitude crossings are finite; unbracketed widths are unavailable. |
| MET-006 | Matched phantom evaluation shall retain fixed ROIs, shared-grid references and per-target validity. | Both modes at 11/75 angles and seven target records are exported, with finite-count and null handling. |
| MET-007 | Output-grid consistency shall preserve amplitude-scale differences at shared coordinates. | A factor-two envelope discrepancy is not hidden by independent normalization; misaligned axes fail. |
| DATA-006 | External analytic evaluation shall explicitly label same-mode full-angle references. | Reports keep separate mode scores and disclaim independent/clinical accuracy; data/settings hashes retained. |
| ALG-014 | Aperture candidate selection shall use predeclared contrast, axial-width and validity guardrails. | Only 11-angle stride-2 records participate; invalid measurements and guardrail violations are excluded; defaults stay unchanged. |
| PERF-004 | Profiling shall separate warmup, repeated timing and sampled working-set passes. | At least two timed repeats; one warmup and one additional RSS pass; raw durations and baseline/peak RSS retained. |
| PERF-005 | Cross-backend profiling shall check full-array agreement where both are measured. | Real and analytic 11-angle RF/B-mode outputs meet existing numerical tolerances. |
| ALG-015 | Optional angle batching shall preserve coherent compounding and physical angle selection. | Non-divisible batches, batch one, oversized batches, real/analytic modes match NumPy; inputs remain unchanged. |
| DATA-007 | The F/0.8 transfer study shall freeze aperture settings without retuning on evaluation acquisitions. | Both F/1.7 and F/0.8 reported per acquisition; unavailable references are null, not self-references labeled as accuracy. |
| PERF-006 | Batched performance comparisons shall use fresh processes and same-F-number unbatched references. | Each measured batch passes full-array RF and B-mode parity against its matching baseline; timing/RSS protocols remain separate. |
| SAFE-001 | Every public-facing description shall identify the software as non-clinical. | README and lifecycle documentation contain the intended-use limitation. |

## Quality attributes

- Reproducibility: fixed seeds, deterministic angle selection, immutable data checks, JSON/CSV
  outputs, and command examples.
- Testability: numerical stages are exposed as small functions with controlled fixtures.
- Traceability: requirements map to tests and generated evidence in the verification plan.
- Portability: the baseline supports Python 3.10 and 3.12; Numba is an optional extra.
- Inspectability: no trained black-box model is used in the image-formation path.

## Explicit exclusions

- No diagnostic claim, clinical decision support, patient-specific recommendation, probe
  control, acoustic-output control, DICOM workflow, or protected-health-information system.
- No claim of compliance with IEC 62304, ISO 14971, ISO 13485, IEC 60601, or a regulatory
  submission requirement.
