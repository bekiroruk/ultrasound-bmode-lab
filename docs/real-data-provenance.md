# Real-data provenance

## Selected datasets

The real-data paths use PICMUS in-vivo carotid cross/longitudinal acquisitions, two physical
PICMUS phantom acquisitions, one Alpinion phantom acquisition, and two selected in-vivo carotid
acquisitions from explicitly distinct EPFL volunteers.

- Dataset record: [USTB datasets, Zenodo DOI 10.5281/zenodo.20261898](https://doi.org/10.5281/zenodo.20261898)
- Catalog entry: [USTB public datasets](https://unioslo.github.io/USTB/datasets.html)
- File: `PICMUS_carotid_cross.uff`
- License shown by Zenodo: **CC BY 4.0**
- Size: 76,705,680 bytes
- Zenodo MD5: `be81dfc519d3f7c642ff60d85642f311`
- UFF-embedded name: `PICMUS challenge in vivo carotid cross`

Additional USTB files:

| File | Bytes | MD5 | Purpose |
|---|---:|---|---|
| `PICMUS_carotid_long.uff` | 76,705,676 | `09fddc4ca1ce2dc9d1ac870a9d3871b6` | In-vivo longitudinal carotid |
| `PICMUS_experiment_contrast_speckle.uff` | 145,518,504 | `26bbfbbb702e90fe4fa9f1ab7d7fc065` | Contrast and speckle statistics |
| `PICMUS_experiment_resolution_distortion.uff` | 145,518,524 | `e8a4487993222f28458aa88259345440` | Resolution and geometric distortion |
| `Alpinion_L3-8_CPWC_hypoechoic.uff` | 48,274,300 | `1b335b36510a2e3406a9f5d575614bdc` | Cross-platform hypoechoic phantom |

USTB describes both as 75-plane-wave measurements from a Verasonics Vantage 256 with an L11
probe on a CIRS Multi-Purpose Ultrasound Phantom Model 040GSE.

The public human UFF file contains no name, date of birth, medical-record number, or other direct
subject identifier. It does contain acquisition data and the citation required by its authors. It
must still be handled as human research data and used only under its published terms.

## EPFL multi-volunteer subset

- Authoritative landing page: [EPFL Ultrafast Ultrasound Dataset](https://www.epfl.ch/labs/lts5/research/us/epfl-ultrafast-ultrasound-datasets/)
- License stated by EPFL: **CC BY 4.0**
- Full collection stated by EPFL: 20,000 in-vivo acquisitions from nine volunteers
- Probe/settings: GE 9L-D, 87 plane waves, 192 receive elements, 20.833 MHz sampling

The study selects carotid acquisitions used in the dataset authors' publications and draws them
from the documented held-out volunteers 005 and 008. Selecting individual ZIP members with HTTP
range requests avoids downloading the complete multi-gigabyte volunteer archives.

| File | Volunteer | Tensor after frame removal | Bytes | ZIP CRC32 | SHA-256 |
|---|---:|---|---:|---:|---|
| `invivo_14965.npz` | 005 | 87 × 192 × 2,133 | 129,470,889 | 3,380,171,651 | `55432c87f1f12aac866a75976cb5680c3d303d5b103076fcd0c18841256c749e` |
| `invivo_18198.npz` | 008 | 87 × 192 × 2,133 | 129,495,251 | 4,287,067,764 | `d82d56f1888e1be5b21cf9302ba95bf97ff91d4b7f79dbe32cff7a89b210b6f0` |

The NPZ metadata exposes the public volunteer ID and body-region label. No direct identity fields
are used or copied into the repository. Raw files remain Git-ignored. EPFL full-angle results are
same-acquisition algorithmic references, not independent anatomical ground truth.

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
record and verifies both size and MD5. `scripts/download_epfl.py` checks member size, ZIP CRC32,
and recorded SHA-256 after selective extraction.

The EPFL subset requires the additional citation:

> R. Viñals and J.-P. Thiran, “Deep Learning-based Inpainting for Sparse Arrays in Ultrafast
> Ultrasound Imaging,” IEEE Transactions on Computational Imaging, 2025.
