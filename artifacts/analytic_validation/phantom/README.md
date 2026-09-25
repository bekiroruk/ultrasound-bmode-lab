# Analytic physical phantom validation

Same RF, angles, F-number 1.7 and stride-2 grid. Measurements use linear envelopes.
The embedded UFF reference is resampled to exactly the same grid.

| Phantom | Angles | Mode | Measurement |
|---|---:|---|---|
| contrast | 11 | legacy | Deep cyst contrast -3.07 dB; CNR 0.402; gCNR 0.268 |
| contrast | 11 | analytic | Deep cyst contrast -20.10 dB; CNR 1.556; gCNR 0.926 |
| contrast | 75 | legacy | Deep cyst contrast -2.61 dB; CNR 0.355; gCNR 0.253 |
| contrast | 75 | analytic | Deep cyst contrast -23.80 dB; CNR 1.626; gCNR 0.934 |
| resolution | 11 | legacy | Median FWHM lateral 0.599 mm; axial 0.679 mm; valid 7/7 |
| resolution | 11 | analytic | Median FWHM lateral 0.652 mm; axial 0.577 mm; valid 7/7 |
| resolution | 75 | legacy | Median FWHM lateral 0.633 mm; axial 0.676 mm; valid 7/7 |
| resolution | 75 | analytic | Median FWHM lateral 0.653 mm; axial 0.575 mm; valid 7/7 |

[Inspect contrast, 11 angles](contrast_11_angles.png) · [Inspect contrast, 75 angles](contrast_75_angles.png) · [Inspect resolution, 11 angles](resolution_11_angles.png) · [Inspect resolution, 75 angles](resolution_75_angles.png)

Half-amplitude width after local 20th-percentile baseline subtraction. Crossings adjacent to an edge are valid if bracketed; truncated crossings are null. Seven nominal targets, with valid-count and per-target results; coarse grid limits precision.

Nominal target positions are approximate, not certified calibration coordinates.
These metrics do not establish clinical performance or confidence intervals.

[Full per-target, shallow/deep cyst and provenance records](metrics.json)
