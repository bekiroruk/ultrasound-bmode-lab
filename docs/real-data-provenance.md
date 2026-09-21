# Real-data provenance

## Selected datasets

The real-data paths use **PICMUS in-vivo carotid cross-section** and two measured physical
phantom acquisitions distributed through the UltraSound ToolBox (USTB) dataset catalog and
archived on Zenodo.

- Dataset record: [USTB datasets, Zenodo DOI 10.5281/zenodo.20261898](https://doi.org/10.5281/zenodo.20261898)
- Catalog entry: [USTB public datasets](https://unioslo.github.io/USTB/datasets.html)
- File: `PICMUS_carotid_cross.uff`
- License shown by Zenodo: **CC BY 4.0**
- Size: 76,705,680 bytes
- Zenodo MD5: `be81dfc519d3f7c642ff60d85642f311`
- UFF-embedded name: `PICMUS challenge in vivo carotid cross`

Additional physical phantom files:

| File | Bytes | MD5 | Purpose |
|---|---:|---|---|
| `PICMUS_experiment_contrast_speckle.uff` | 145,518,504 | `26bbfbbb702e90fe4fa9f1ab7d7fc065` | Contrast and speckle statistics |
| `PICMUS_experiment_resolution_distortion.uff` | 145,518,524 | `e8a4487993222f28458aa88259345440` | Resolution and geometric distortion |

USTB describes both as 75-plane-wave measurements from a Verasonics Vantage 256 with an L11
probe on a CIRS Multi-Purpose Ultrasound Phantom Model 040GSE.

The public human UFF file contains no name, date of birth, medical-record number, or other direct
subject identifier. It does contain acquisition data and the citation required by its authors. It
must still be handled as human research data and used only under its published terms.

## Acquisition metadata read from the UFF file

| Field | Value |
|---|---:|
| Plane-wave transmissions | 75 |
| Receive elements | 128 |
| RF samples per channel | 1,536 |
| Sampling frequency | 20.832 MHz |
| Assumed sound speed | 1,540 m/s |
| Steering range | −16° to +16° |
| Probe pitch | 0.300 mm |
| Element width | 0.270 mm |
| Element height | 5.000 mm |

Published descriptions identify the acquisition platform as a Verasonics Vantage 256 research scanner with an L11/L11-4v linear probe. The implementation treats the numerical metadata inside the UFF file as authoritative for reconstruction.

## Required citation

The UFF file embeds the following reference:

> H. Liebgott, A. Rodriguez-Molares, F. Cervenansky, J. A. Jensen and O. Bernard, “Plane-Wave Imaging Challenge in Medical Ultrasound,” 2016 IEEE International Ultrasonics Symposium (IUS), Tours, 2016, pp. 1–4. doi: 10.1109/ULTSYM.2016.7728908.

The datasets are not committed to Git. `scripts/download_picmus.py` retrieves the immutable Zenodo
record and verifies both size and MD5 before use.
