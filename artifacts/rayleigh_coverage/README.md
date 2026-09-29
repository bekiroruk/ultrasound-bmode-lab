# Rayleigh-model gCNR coverage stress test

Synthetic envelopes, not RF or patient data. Rayleigh MLE scales and exact two-Rayleigh density overlap; fixed ROI. Pixel IID, offset 4x4 constant tiles, and misspecified IID lognormal stress. Block origins 0 and 2 were fixed from the generator geometry, never selected from results. Independent random fields across scenarios; same field across block options. Percentile resampling treats occupied 1x1 or 8x8 tiles as units and preserves partial ROI masks.

A Rayleigh model is not established for human tissue, adaptive beamformers or all phantoms. Better coverage on its generating model cannot validate intervals for measured RF. Aligned blocks require knowledge of correlation geometry; this experiment does not estimate it. Lognormal stress uses a known non-Rayleigh population and deliberately tests model failure. Finite Monte Carlo uncertainty is summarized by Wilson intervals; no calibration on these evaluation trials, no automatic replacement of the 64-bin metric.

200 independent fields/scenario; 300 resamples/interval.
Rayleigh truth: 0.472470; lognormal truth: 0.379474.
Source: [Schlunk & Byram (2023)](https://lab.vanderbilt.edu/beamlab/wp-content/uploads/sites/191/2024/04/schlunk_2023_gcnr.pdf).

| Scenario | Block | Origin | Coverage | Wilson 95% | Bias | Width |
|---|---:|---:|---:|---|---:|---:|
| iid_rayleigh | 1 | 0 | 0.930 | [0.886, 0.958] | -0.0016 | 0.0888 |
| iid_rayleigh | 8 | 0 | 0.865 | [0.811, 0.906] | -0.0016 | 0.0857 |
| offset_correlated_rayleigh | 1 | 0 | 0.405 | [0.339, 0.474] | -0.0078 | 0.0826 |
| offset_correlated_rayleigh | 8 | 0 | 0.835 | [0.777, 0.880] | -0.0078 | 0.2308 |
| offset_correlated_rayleigh | 8 | 2 | 0.890 | [0.839, 0.926] | -0.0078 | 0.2979 |
| iid_lognormal_stress | 1 | 0 | 0.470 | [0.402, 0.539] | +0.0944 | 0.1925 |

This is a conditional model diagnostic, not a general solution for measured ultrasound or calibrated clinical intervals.

![Coverage by scenario and block](coverage.png)

[All independent trials](metrics.json)
