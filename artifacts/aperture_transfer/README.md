# Frozen aperture transfer check

Five acquisitions excluded from the aperture sweep, but already inspected in earlier project stages. This is a frozen-parameter transfer check, not a new blinded or clinical validation. No population generalization; defaults remain unchanged.

PICMUS: embedded UFF image, algorithmic reference not anatomical ground truth. EPFL/Alpinion: no independent reference; aperture-change similarity only describes how much the output changed and is not a quality score.

| Acquisition | Angles | Embedded reference SSIM F/1.7 → F/0.8 | Batch parity |
|---|---:|---:|---|
| picmus_cross | 11 | 0.456 → 0.420 | Both F-numbers passed |
| picmus_cross | 75 | 0.715 → 0.654 | Both F-numbers passed |
| picmus_long | 11 | 0.554 → 0.501 | Both F-numbers passed |
| picmus_long | 75 | 0.748 → 0.650 | Both F-numbers passed |
| epfl_v5 | 11 | Unavailable; no independent reference | Both F-numbers passed |
| epfl_v5 | 87 | Unavailable; no independent reference | Both F-numbers passed |
| epfl_v8 | 11 | Unavailable; no independent reference | Both F-numbers passed |
| epfl_v8 | 87 | Unavailable; no independent reference | Both F-numbers passed |
| alpinion_phantom | 11 | Unavailable; no independent reference | Both F-numbers passed |
| alpinion_phantom | 21 | Unavailable; no independent reference | Both F-numbers passed |

Every reconstruction compared to the unbatched path using the same F-number, angles and coordinates. RF rtol=1e-5/atol=1e-7; B-mode atol=1e-4 dB, rtol=0.

## Images

- [PICMUS carotid · cross](picmus_cross.png)
- [PICMUS carotid · longitudinal](picmus_long.png)
- [EPFL volunteer 005 · carotid](epfl_v5.png)
- [EPFL volunteer 008 · carotid](epfl_v8.png)
- [Alpinion · hypoechoic phantom](alpinion_phantom.png)

[Complete metrics, data/settings hashes and geometry](metrics.json)
