# Frozen interpolation transfer check

Frozen-parameter transfer of v0.9 cubic interpolation to measured PICMUS and EPFL human acquisitions plus an Alpinion physical phantom. No parameter selection or default change; these cases were excluded from the v0.9 phantom study but have already been inspected in earlier project stages.

Only embedded UFF images provide reference similarity, and are same-acquisition algorithmic references, not anatomical ground truth. EPFL and Alpinion have no independent image reference: their reference scores are unavailable (null). Linear/cubic change similarity is not a quality score for any acquisition.

Each reconstruction uses its own peak-normalized 60 dB B-mode image. Embedded references are normalized on their full native grid before stride sampling. No cropping, alignment, denoising or intensity matching is applied.

F/1.7, analytic channel processing, batch 8, cache preparation batch 8 and each acquisition's metadata sound speed are fixed. Embedded-reference cases use stride 2; cases without an embedded reference use stride 1. No parameter is tuned here.

| Acquisition | Angles | Embedded reference SSIM: linear → cubic | Linear/cubic change SSIM (not quality) | Cubic cache/batch parity |
|---|---:|---:|---:|---|
| picmus_cross | 11 | 0.4561 → 0.4583 | 0.9879 | Passed |
| picmus_cross | 75 | 0.7152 → 0.7061 | 0.9917 | Passed |
| picmus_long | 11 | 0.5541 → 0.5543 | 0.9907 | Passed |
| picmus_long | 75 | 0.7478 → 0.7422 | 0.9962 | Passed |
| epfl_v5 | 11 | Unavailable | 0.9894 | Passed |
| epfl_v5 | 87 | Unavailable | 0.9948 | Passed |
| epfl_v8 | 11 | Unavailable | 0.9943 | Passed |
| epfl_v8 | 87 | Unavailable | 0.9978 | Passed |
| alpinion_phantom | 11 | Unavailable | 0.9987 | Passed |
| alpinion_phantom | 21 | Unavailable | 0.9989 | Passed |

For every acquisition and angle count, cached batch-8 cubic reconstruction is checked against uncached unbatched cubic at exactly the same coordinates and angle order. RF rtol=1e-5/atol=1e-7; B-mode rtol=0/atol=1e-4 dB.

## Images

- [PICMUS carotid · cross](picmus_cross.png)
- [PICMUS carotid · longitudinal](picmus_long.png)
- [EPFL volunteer 005 · carotid](epfl_v5.png)
- [EPFL volunteer 008 · carotid](epfl_v8.png)
- [Alpinion · hypoechoic phantom](alpinion_phantom.png)

Each row compares the same angles and physical coordinates. The difference maps use a fixed ±6 dB display limit; metrics use the complete, unclipped differences.

The two PICMUS views are not assumed to represent two distinct people. Only the two EPFL volunteer IDs establish distinct participants. These acquisitions were already inspected in previous project stages, so this is not a blinded validation.

No runtime comparison or clinical quality claim is made. Cache preparation duration is retained for traceability only.

[Complete measurements, array geometry, angle selections and source hashes](metrics.json)
