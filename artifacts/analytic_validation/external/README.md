# External analytic validation

No independent reference is available. For each mode, 11 angles are compared only to that same mode's full-angle reconstruction. Do not interpret this as accuracy or compare these SSIM values as evidence that one mode is superior.

| Acquisition | Mode | 11/full SSIM | Grid envelope NRMSE |
|---|---|---:|---:|
| epfl_v5 | legacy | 0.685 | 0.024837 |
| epfl_v5 | analytic | 0.536 | 0.000000 |
| epfl_v8 | legacy | 0.759 | 0.029928 |
| epfl_v8 | analytic | 0.594 | 0.000000 |
| alpinion_phantom | legacy | 0.897 | 0.035410 |
| alpinion_phantom | analytic | 0.930 | 0.000000 |

11-angle linear envelope on stride-2 grid vs shared pixels from stride-1 grid; normalized by the fine-grid shared envelope peak. This tests numerical grid consistency, not anatomical correctness. Analytic invariance follows by construction.

Two public EPFL volunteer acquisitions and one Alpinion physical phantom only.
[Volunteer 005](epfl_v5.png) · [Volunteer 008](epfl_v8.png) · [Alpinion phantom](alpinion_phantom.png)

[Full metrics, settings and data checksums](metrics.json)
