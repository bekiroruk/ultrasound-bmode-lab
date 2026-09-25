# Analytic receive-aperture study

Select minimum median lateral FWHM at 11 angles / stride 2, requiring all seven widths valid in both directions, median axial FWHM <= 1.05 times baseline, and each cyst gCNR no more than 0.02 below baseline. Includes baseline as fallback.

Selected exploratory candidate: **F/0.8**. No reconstruction defaults changed.

Exploratory selection on the measured phantom, not independent validation. 75-angle and finer-grid checks reuse these same acquisitions. No defaults changed; do not claim generalization to human data or clinical benefit. The candidate may lie at the sweep boundary; this is not evidence of a global optimum.

| Angles | Grid stride | F-number | Lateral FWHM mm | Axial FWHM mm | Shallow gCNR | Deep gCNR |
|---:|---:|---:|---:|---:|---:|---:|
| 11 | 2 | 0.8 | 0.5719 | 0.5812 | 0.9215 | 0.9286 |
| 11 | 2 | 1.0 | 0.5787 | 0.5762 | 0.9336 | 0.9277 |
| 11 | 2 | 1.2 | 0.6023 | 0.5758 | 0.9273 | 0.9262 |
| 11 | 2 | 1.5 | 0.6310 | 0.5763 | 0.9273 | 0.9255 |
| 11 | 2 | 1.7 | 0.6516 | 0.5773 | 0.9283 | 0.9262 |
| 11 | 2 | 2.0 | 0.6772 | 0.5784 | 0.9288 | 0.9201 |
| 11 | 2 | 2.5 | 0.7059 | 0.5786 | 0.9315 | 0.9051 |
| 75 | 2 | 0.8 | 0.5786 | 0.5747 | 0.9635 | 0.9306 |
| 75 | 2 | 1.0 | 0.5862 | 0.5740 | 0.9710 | 0.9325 |
| 75 | 2 | 1.2 | 0.6053 | 0.5756 | 0.9668 | 0.9385 |
| 75 | 2 | 1.5 | 0.6337 | 0.5758 | 0.9681 | 0.9420 |
| 75 | 2 | 1.7 | 0.6530 | 0.5746 | 0.9681 | 0.9337 |
| 75 | 2 | 2.0 | 0.6781 | 0.5742 | 0.9715 | 0.9302 |
| 75 | 2 | 2.5 | 0.7043 | 0.5719 | 0.9620 | 0.9269 |
| 11 | 1 | 1.7 | 0.6410 | 0.5780 | 0.9370 | 0.9159 |
| 11 | 1 | 0.8 | 0.5522 | 0.5756 | 0.9259 | 0.9273 |

![Tradeoffs](aperture_tradeoffs.png)

[Fine-grid contrast](contrast_fine.png) · [Fine-grid resolution](resolution_fine.png)

[All points, measurements and data provenance](metrics.json)
