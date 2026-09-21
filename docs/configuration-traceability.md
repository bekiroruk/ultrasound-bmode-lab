# Configuration and data traceability

## Data configuration items

| Alias | File | Bytes | MD5 | Purpose |
|---|---|---:|---|---|
| carotid | `PICMUS_carotid_cross.uff` | 76,705,680 | `be81dfc519d3f7c642ff60d85642f311` | In-vivo carotid reconstruction and ROI analysis |
| carotid-long | `PICMUS_carotid_long.uff` | 76,705,676 | `09fddc4ca1ce2dc9d1ac870a9d3871b6` | Independent anatomical-view reconstruction |
| contrast | `PICMUS_experiment_contrast_speckle.uff` | 145,518,504 | `26bbfbbb702e90fe4fa9f1ab7d7fc065` | Physical CIRS cyst and speckle metrics |
| resolution | `PICMUS_experiment_resolution_distortion.uff` | 145,518,524 | `e8a4487993222f28458aa88259345440` | Physical CIRS point-target and distortion metrics |
| alpinion | `Alpinion_L3-8_CPWC_hypoechoic.uff` | 48,274,300 | `1b335b36510a2e3406a9f5d575614bdc` | Cross-platform phantom reconstruction |

All files come from Zenodo record `10.5281/zenodo.20261898` and are stored under ignored
`data/raw/`. `scripts/download_picmus.py` is the controlled retrieval interface.

| EPFL alias | File | Bytes | SHA-256 | Purpose |
|---|---|---:|---|---|
| v5-carotid | `epfl/invivo_14965.npz` | 129,470,889 | `55432c87f1f12aac866a75976cb5680c3d303d5b103076fcd0c18841256c749e` | Held-out volunteer 005 sparse-angle study |
| v8-carotid | `epfl/invivo_18198.npz` | 129,495,251 | `d82d56f1888e1be5b21cf9302ba95bf97ff91d4b7f79dbe32cff7a89b210b6f0` | Held-out volunteer 008 sparse-angle study |

These files and their settings come from the EPFL Ultrafast Ultrasound Dataset. The controlled
retrieval interface is `scripts/download_epfl.py`; it also validates member CRC32 values.

## Software configuration items

- Source revision: Git commit SHA.
- Python compatibility baseline: 3.10 and 3.12 in GitHub Actions.
- Core dependencies: NumPy, SciPy, Matplotlib, h5py, psutil.
- Optional compiled backend: Numba/LLVM.
- Parameters: CLI arguments plus values embedded in generated JSON.
- Evidence: versioned PNG, JSON, and CSV files under `artifacts/`.

For a formal experiment record, retain the commit SHA, operating system, Python version,
dependency freeze, command line, dataset hash, generated JSON, and wall-clock timestamp.

## Change-control rule

A change to propagation delay, interpolation, aperture, compounding, envelope processing, ROI
geometry, or a metric formula requires:

1. a focused unit test or revised acceptance criterion;
2. regeneration of the affected evidence artifact;
3. comparison with the preceding JSON result;
4. explanation of unexpected numerical or visual changes; and
5. review of related entries in `risk-management.md`.
