# Channel-analytic reconstruction comparison

Measured RF only. Each before/after pair uses identical angles, aperture and grid.
Reference: independently stored UFF beamformed image (not anatomical ground truth).

| Acquisition | Angles | SSIM before → after | RMSE dB before → after | Figure |
|---|---:|---:|---:|---|
| PICMUS_carotid_cross | 11 | 0.271 → 0.457 | 9.59 → 6.95 | [Compare](PICMUS_carotid_cross_11_angles.png) |
| PICMUS_carotid_cross | 75 | 0.462 → 0.731 | 8.07 → 4.84 | [Compare](PICMUS_carotid_cross_75_angles.png) |
| PICMUS_carotid_long | 11 | 0.365 → 0.560 | 9.08 → 6.41 | [Compare](PICMUS_carotid_long_11_angles.png) |
| PICMUS_carotid_long | 75 | 0.460 → 0.749 | 8.49 → 5.45 | [Compare](PICMUS_carotid_long_75_angles.png) |
| PICMUS_experiment_contrast_speckle | 11 | 0.417 → 0.848 | 9.08 → 6.89 | [Compare](PICMUS_experiment_contrast_speckle_11_angles.png) |
| PICMUS_experiment_contrast_speckle | 75 | 0.440 → 0.930 | 9.02 → 6.32 | [Compare](PICMUS_experiment_contrast_speckle_75_angles.png) |
| PICMUS_experiment_resolution_distortion | 11 | 0.397 → 0.708 | 9.17 → 8.86 | [Compare](PICMUS_experiment_resolution_distortion_11_angles.png) |
| PICMUS_experiment_resolution_distortion | 75 | 0.428 → 0.795 | 8.83 → 8.29 | [Compare](PICMUS_experiment_resolution_distortion_75_angles.png) |

Settings: numba; axial/lateral stride 2; F-number 1.5; 60 dB.

Each image peak-normalized; reference normalized before grid subsampling.

Reference similarity is not ground-truth or clinical accuracy. Analytic RF is not baseband IQ. No denoising, sharpening, registration, or contrast optimization. CUDA and native C++ paths remain legacy real-RF only.

Exact selected indices, file SHA-256 values and metrics: [JSON](quality_metrics.json).
