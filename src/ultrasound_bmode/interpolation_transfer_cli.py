"""Evaluate frozen linear/cubic interpolation on measured human and device RF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .accelerated import numba_plane_wave_delay_and_sum, prepare_analytic_channel_cache
from .analytic_validation_cli import _base_report, _provenance, finite_json
from .aperture_transfer_cli import compare_reconstructions
from .external_validation_cli import _cases, _load
from .metrics import evaluate_similarity
from .real_data import reference_bmode, select_transmit_indices
from .reconstruction_quality_cli import _sha256

SETTINGS_FILES = ("beamforming_settings.yaml", "steering_angles.npy", "time_axis.npy")


def _validate_geometry(acquisition, result, stride, count):
    """Reject silent cropping, angle substitution, or malformed reconstruction arrays."""
    x = acquisition.x_axis_m[::stride]
    z = acquisition.z_axis_m[::stride]
    np.testing.assert_array_equal(result.x_axis_m, x)
    np.testing.assert_array_equal(result.z_axis_m, z)
    np.testing.assert_array_equal(
        result.angle_indices, select_transmit_indices(acquisition.transmit_angles_rad, count)
    )
    if result.rf.shape != (z.size, x.size) or result.bmode_db.shape != (z.size, x.size):
        raise AssertionError("Reconstruction array shape does not match its physical grid")


def _save_comparison(case, comparisons, output):
    """Show matched images and signed change; use dedicated colorbars and tight bounds."""
    fig, axes = plt.subplots(
        len(comparisons), 3, figsize=(13, 4.7 * len(comparisons)),
        squeeze=False, layout="constrained",
    )
    for row, (count, linear, cubic) in enumerate(comparisons):
        x, z = cubic.x_axis_m * 1e3, cubic.z_axis_m * 1e3
        extent = (x[0], x[-1], z[-1], z[0])
        for column, (name, image) in enumerate((
            ("Linear", linear.bmode_db), ("Cubic", cubic.bmode_db),
            ("Cubic minus linear", cubic.bmode_db - linear.bmode_db),
        )):
            axis = axes[row, column]
            is_change = column == 2
            display = axis.imshow(
                image, extent=extent, aspect="equal", interpolation="nearest",
                cmap="RdBu_r" if is_change else "gray",
                vmin=-6 if is_change else -60, vmax=6 if is_change else 0,
            )
            axis.set(title=f"{name}\n{count} angles", xlabel="Lateral [mm]", ylabel="Depth [mm]")
            label = "Change [dB; display clipped at ±6]" if is_change else "Amplitude [dB]"
            fig.colorbar(display, ax=axis, shrink=0.75, label=label)
    fig.suptitle(
        case.label + "\nFrozen F/1.7 · analytic RF · acquisition sound speed\n"
        "Change maps describe output differences, not improved anatomical accuracy",
        fontsize=12,
    )
    fig.savefig(output, dpi=150, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)


def _save_report(report, output_dir):
    lines = [
        "# Frozen interpolation transfer check", "", report["scope"], "",
        report["reference_policy"], "", report["normalization_policy"], "",
        ("F/1.7, analytic channel processing, batch 8, cache preparation batch 8 and each "
        "acquisition's metadata sound speed are fixed. Embedded-reference cases use stride 2; "
        "cases without an embedded reference use stride 1. No parameter is tuned here."), "",
        ("| Acquisition | Angles | Embedded reference SSIM: linear → cubic | "
        "Linear/cubic change SSIM (not quality) | Cubic cache/batch parity |"),
        "|---|---:|---:|---:|---|",
    ]
    for row in report["records"]:
        scores = row["embedded_reference_similarity"]
        reference = (
            f"{scores['linear']['ssim']:.4f} → {scores['cubic']['ssim']:.4f}"
            if scores is not None else "Unavailable"
        )
        lines.append(
            f"| {row['case']} | {row['angle_count']} | {reference} | "
            f"{row['interpolation_change_not_quality']['ssim']:.4f} | Passed |"
        )
    lines += ["", report["parity_policy"], "", "## Images", ""]
    lines += [f"- [{item['label']}]({item['case']}.png)" for item in report["datasets"]]
    lines += [
        "", ("Each row compares the same angles and physical coordinates. The difference "
        "maps use a fixed ±6 dB display limit; metrics use the complete, unclipped differences."),
        "", ("The two PICMUS views are not assumed to represent two distinct people. Only "
        "the two EPFL volunteer IDs establish distinct participants. These acquisitions were "
        "already inspected in previous project stages, so this is not a blinded validation."),
        "", ("No runtime comparison or clinical quality claim is made. Cache preparation "
        "duration is retained for traceability only."), "",
        "[Complete measurements, array geometry, angle selections and source hashes](metrics.json)",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "metrics.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def run_interpolation_transfer(data_dir: Path, output_dir: Path):
    cases = _cases(data_dir)
    required = [case.path for case in cases]
    if any(case.loader == "epfl" for case in cases):
        required.extend(data_dir / "epfl/settings" / name for name in SETTINGS_FILES)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing interpolation transfer data:\n" + "\n".join(missing))
    output_dir.mkdir(parents=True, exist_ok=True)
    report = _base_report("Frozen cubic interpolation transfer to measured RF acquisitions")
    report.update({
        "settings": {
            "f_number": 1.7, "analytic": True, "angle_batch_size": 8,
            "cache_preparation_batch_size": 8, "sound_speed": "acquisition metadata",
            "embedded_reference_stride": 2, "no_reference_stride": 1,
            "interpolations": ["linear", "cubic"], "angle_counts": "11 and all acquired",
        },
        "scope": (
            "Frozen-parameter transfer of v0.9 cubic interpolation to measured PICMUS and "
            "EPFL human acquisitions plus an Alpinion physical phantom. No parameter "
            "selection or default change; these cases were excluded from the v0.9 phantom "
            "study but have already been inspected in earlier project stages."
        ),
        "reference_policy": (
            "Only embedded UFF images provide reference similarity, and are same-acquisition "
            "algorithmic references, not anatomical ground truth. EPFL and Alpinion have no "
            "independent image reference: their reference scores are unavailable (null). "
            "Linear/cubic change similarity is not a quality score for any acquisition."
        ),
        "normalization_policy": (
            "Each reconstruction uses its own peak-normalized 60 dB B-mode image. Embedded "
            "references are normalized on their full native grid before stride sampling. "
            "No cropping, alignment, denoising or intensity matching is applied."
        ),
        "parity_policy": (
            "For every acquisition and angle count, cached batch-8 cubic reconstruction is "
            "checked against uncached unbatched cubic at exactly the same coordinates and "
            "angle order. RF rtol=1e-5/atol=1e-7; B-mode rtol=0/atol=1e-4 dB."
        ),
        "parity_tolerances": {"rf_rtol": 1e-5, "rf_atol": 1e-7,
                              "bmode_rtol": 0, "bmode_atol_db": 1e-4},
    })
    for case in cases:
        acquisition = _load(case, data_dir)
        full_count = int(acquisition.transmit_angles_rad.size)
        if full_count < 11:
            raise ValueError(f"{case.identifier} has fewer than the required 11 angles")
        metadata = _provenance(case.path, acquisition)
        metadata.update(case=case.identifier, label=case.label, subject=case.subject,
                        probe=case.probe, platform=case.platform, anatomy=case.anatomy)
        if case.loader == "epfl":
            metadata["settings_sha256"] = {
                name: _sha256(data_dir / "epfl/settings" / name) for name in SETTINGS_FILES
            }
        cache = prepare_analytic_channel_cache(acquisition, batch_size=8)
        metadata["analytic_cache"] = {
            "size_mib": cache.size_mib, "preparation_seconds_not_benchmark": cache.preparation_seconds,
            "preparation_batch_size": cache.preparation_batch_size,
        }
        report["datasets"].append(metadata)
        stride = 2 if acquisition.reference_iq is not None else 1
        reference = (reference_bmode(acquisition)[::stride, ::stride]
                     if acquisition.reference_iq is not None else None)
        comparisons = []
        for count in dict.fromkeys((11, full_count)):
            kwargs = {
                "angle_count": count, "f_number": 1.7, "analytic": True,
                "axial_stride": stride, "lateral_stride": stride, "dynamic_range_db": 60,
            }
            outputs = {}
            for interpolation in ("linear", "cubic"):
                result = numba_plane_wave_delay_and_sum(
                    acquisition, interpolation=interpolation, angle_batch_size=8,
                    analytic_cache=cache, **kwargs,
                )
                _validate_geometry(acquisition, result, stride, count)
                outputs[interpolation] = result
            unbatched = numba_plane_wave_delay_and_sum(
                acquisition, interpolation="cubic", **kwargs,
            )
            _validate_geometry(acquisition, unbatched, stride, count)
            cubic, linear = outputs["cubic"], outputs["linear"]
            parity = compare_reconstructions(unbatched, cubic)
            scores = ({name: evaluate_similarity(reference, result.bmode_db).to_dict()
                       for name, result in outputs.items()} if reference is not None else None)
            report["records"].append({
                "case": case.identifier, "angle_count": count, "acquired_angle_count": full_count,
                "angle_indices": cubic.angle_indices.tolist(), "stride": stride,
                "sound_speed_m_s": acquisition.sound_speed_m_s,
                "output_shape": list(cubic.bmode_db.shape),
                "x_axis_m": cubic.x_axis_m.tolist(), "z_axis_m": cubic.z_axis_m.tolist(),
                "reference_type": "embedded UFF" if reference is not None else "unavailable",
                "embedded_reference_similarity": scores,
                "interpolation_change_not_quality": evaluate_similarity(
                    linear.bmode_db, cubic.bmode_db
                ).to_dict(),
                "cubic_cache_batch_parity": parity,
            })
            comparisons.append((count, linear, cubic))
            print(f"{case.identifier}, {count} angles: cubic cache/batch parity passed", flush=True)
        _save_comparison(case, comparisons, output_dir / f"{case.identifier}.png")
        # Release the complete source/quadrature tensors before loading the next acquisition.
        del cache, acquisition
    clean = finite_json(report)
    _save_report(clean, output_dir)
    return clean


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/interpolation_transfer"))
    args = parser.parse_args()
    run_interpolation_transfer(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
