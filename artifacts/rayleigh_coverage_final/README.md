# Rayleigh-model gCNR coverage stress test

Synthetic envelopes, not RF or patient data. Rayleigh MLE scales and exact two-Rayleigh density overlap; fixed ROI. Pixel IID, offset 4x4 constant tiles, and misspecified IID lognormal stress. Block origins 0 and 2 were fixed from the generator geometry, never selected from results. Independent random fields across scenarios; same field across block options. Percentile resampling treats occupied 1x1, 4x4 or 8x8 tiles as units and preserves partial ROI masks.

A Rayleigh model is not established for human tissue, adaptive beamformers or all phantoms. Better coverage on its generating model cannot validate intervals for measured RF. Aligned blocks require knowledge of correlation geometry; this experiment does not estimate it. The basic interval reflects bootstrap quantiles around the point estimate and is evaluated on a fresh seed after the initial percentile runs. Lognormal stress uses a known non-Rayleigh population and deliberately tests model failure. Finite Monte Carlo uncertainty is summarized by Wilson intervals; no calibration on these evaluation trials, no automatic replacement of the 64-bin metric.

200 independent fields/scenario; 300 resamples/interval.
Rayleigh truth: 0.472470; lognormal truth: 0.379474.
Source: [Schlunk & Byram (2023)](https://lab.vanderbilt.edu/beamlab/wp-content/uploads/sites/191/2024/04/schlunk_2023_gcnr.pdf).

| Scenario | Block | Origin | Percentile | Basic | Bias | Width |
|---|---:|---:|---:|---:|---:|---:|
| iid_rayleigh | 1 | 0 | 0.960 | 0.960 | -0.0033 | 0.0884 |
| iid_rayleigh | 8 | 0 | 0.925 | 0.920 | -0.0033 | 0.0910 |
| offset_correlated_rayleigh | 1 | 0 | 0.315 | 0.310 | +0.0043 | 0.0816 |
| offset_correlated_rayleigh | 4 | 2 | 0.890 | 0.880 | +0.0043 | 0.2964 |
| offset_correlated_rayleigh | 8 | 0 | 0.720 | 0.685 | +0.0043 | 0.2311 |
| offset_correlated_rayleigh | 8 | 2 | 0.880 | 0.805 | +0.0043 | 0.3001 |
| iid_lognormal_stress | 1 | 0 | 0.450 | 0.415 | +0.0957 | 0.1903 |

Wilson 95% intervals for both observed coverage frequencies are stored in metrics.json.

This is a conditional model diagnostic, not a general solution for measured ultrasound or calibrated clinical intervals.

![Coverage by scenario and block](coverage.png)

[All independent trials](metrics.json)
