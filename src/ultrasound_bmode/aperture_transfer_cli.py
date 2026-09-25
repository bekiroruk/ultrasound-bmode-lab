"""Check a frozen phantom-selected aperture on acquisitions excluded from its sweep."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .accelerated import numba_plane_wave_delay_and_sum
from .analytic_validation_cli import _base_report, _provenance, _save_panels, finite_json
from .external_validation_cli import _cases, _load
from .metrics import evaluate_similarity
from .real_data import reference_bmode
from .reconstruction_quality_cli import _sha256


def compare_reconstructions(reference, candidate):
    """Require like-for-like geometry and angles before checking batched parity."""
    for name in ("angle_indices", "x_axis_m", "z_axis_m"):
        np.testing.assert_array_equal(getattr(candidate, name), getattr(reference, name))
    np.testing.assert_allclose(candidate.rf, reference.rf, rtol=1e-5, atol=1e-7)
    np.testing.assert_allclose(candidate.bmode_db, reference.bmode_db, rtol=0, atol=1e-4)
    return {
        "passed": True,
        "rf_max_absolute_error": float(np.max(np.abs(candidate.rf - reference.rf))),
        "bmode_max_absolute_error_db": float(np.max(np.abs(candidate.bmode_db - reference.bmode_db))),
    }


def run_transfer(data_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    report = _base_report("Frozen F/0.8 aperture transfer and angle-batch equivalence")
    report.update({
        "baseline_f_number": 1.7, "candidate_f_number": 0.8, "batch_size": 16,
        "selection_source": "v0.6 PICMUS contrast/resolution phantom sweep; no retuning here",
        "scope": (
            "Five acquisitions excluded from the aperture sweep, but already inspected in earlier "
            "project stages. This is a frozen-parameter transfer check, not a new blinded or "
            "clinical validation. No population generalization; defaults remain unchanged."
        ),
        "reference_policy": (
            "PICMUS: embedded UFF image, algorithmic reference not anatomical ground truth. "
            "EPFL/Alpinion: no independent reference; aperture-change similarity only describes "
            "how much the output changed and is not a quality score."
        ),
        "batch_policy": (
            "Every reconstruction compared to the unbatched path using the same F-number, "
            "angles and coordinates. RF rtol=1e-5/atol=1e-7; B-mode atol=1e-4 dB, rtol=0."
        ),
    })
    lines = ["# Frozen aperture transfer check", "", report["scope"], "",
             report["reference_policy"], "",
             "| Acquisition | Angles | Embedded reference SSIM F/1.7 → F/0.8 | Batch parity |",
             "|---|---:|---:|---|"]
    for case in _cases(data_dir):
        acquisition = _load(case, data_dir)
        metadata = _provenance(case.path, acquisition)
        metadata.update(subject=case.subject, probe=case.probe, platform=case.platform)
        if case.loader == "epfl":
            metadata["settings_sha256"] = {
                name: _sha256(data_dir / "epfl/settings" / name)
                for name in ("beamforming_settings.yaml", "steering_angles.npy", "time_axis.npy")
            }
        report["datasets"].append(metadata)
        stride = 2 if acquisition.reference_iq is not None else 1
        reference = reference_bmode(acquisition)[::stride, ::stride] if stride == 2 else None
        panels = []
        for count in (11, acquisition.transmit_angles_rad.size):
            outputs, metrics, parity = {}, {}, {}
            for f_number in (1.7, 0.8):
                kwargs = {"angle_count": int(count), "f_number": f_number, "analytic": True,
                          "axial_stride": stride, "lateral_stride": stride}
                unbatched = numba_plane_wave_delay_and_sum(acquisition, **kwargs)
                batched = numba_plane_wave_delay_and_sum(acquisition, angle_batch_size=16, **kwargs)
                parity[str(f_number)] = compare_reconstructions(unbatched, batched)
                outputs[f_number] = batched
                metrics[str(f_number)] = (evaluate_similarity(reference, batched.bmode_db).to_dict()
                                          if reference is not None else None)
                panels.append((f"F/{f_number} · {count} angles", batched.bmode_db))
                print(f"{case.identifier}, {count} angles, F/{f_number}: batch parity passed",
                      flush=True)
            report["records"].append({
                "case": case.identifier, "angle_count": int(count), "stride": stride,
                "angle_indices": batched.angle_indices.tolist(),
                "reference_type": "embedded UFF" if reference is not None else "unavailable",
                "embedded_reference_similarity": metrics,
                "aperture_change_not_quality": evaluate_similarity(
                    outputs[1.7].bmode_db, outputs[0.8].bmode_db
                ).to_dict(),
                "batch_parity": parity,
            })
            score = (f"{metrics['1.7']['ssim']:.3f} → {metrics['0.8']['ssim']:.3f}"
                     if reference is not None else "Unavailable; no independent reference")
            lines.append(f"| {case.identifier} | {count} | {score} | Both F-numbers passed |")
        _save_panels(panels, batched.x_axis_m, batched.z_axis_m,
                     output_dir / f"{case.identifier}.png",
                     case.label + "\nFrozen F/0.8 transfer · not a clinical validation")
    lines += ["", report["batch_policy"], "",
              "## Images", ""] + [f"- [{case.label}]({case.identifier}.png)" for case in _cases(data_dir)]
    lines += ["", "[Complete metrics, data/settings hashes and geometry](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    clean = finite_json(report)
    (output_dir / "metrics.json").write_text(json.dumps(clean, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    return clean


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/aperture_transfer"))
    args = parser.parse_args()
    run_transfer(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
