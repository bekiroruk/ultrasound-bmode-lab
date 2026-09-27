"""Compare delay interpolation and sound-speed sensitivity on measured phantoms."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .accelerated import numba_plane_wave_delay_and_sum, prepare_analytic_channel_cache
from .analytic_validation_cli import _base_report, _measure, _provenance, _save_panels, finite_json
from .metrics import evaluate_similarity
from .processing import log_compress
from .real_data import load_picmus_uff

SOUND_SPEEDS_M_S = (1460.0, 1500.0, 1540.0, 1580.0, 1620.0)


def _reconstruct(acquisition, cache, kind, interpolation, sound_speed, angle_count):
    adjusted = replace(acquisition, sound_speed_m_s=sound_speed)
    start = time.perf_counter()
    result = numba_plane_wave_delay_and_sum(
        adjusted,
        angle_count=angle_count,
        f_number=1.7,
        analytic=True,
        lateral_stride=2,
        axial_stride=2,
        angle_batch_size=8,
        analytic_cache=cache,
        interpolation=interpolation,
    )
    elapsed = time.perf_counter() - start
    envelope = np.abs(result.rf)
    reference_bmode = log_compress(np.abs(acquisition.reference_iq)[::2, ::2], 60)
    return result, {
        "kind": kind,
        "interpolation": interpolation,
        "sound_speed_m_s": sound_speed,
        "angle_count": angle_count,
        "angle_indices": result.angle_indices.tolist(),
        "wall_seconds_not_benchmark": elapsed,
        "metrics": _measure(kind, envelope, result.x_axis_m, result.z_axis_m),
        "embedded_reference_similarity": evaluate_similarity(
            reference_bmode, result.bmode_db
        ).to_dict(),
    }


def _plot_sound_speed(records, output):
    by_kind = {
        kind: sorted(
            [row for row in records if row["kind"] == kind],
            key=lambda row: row["sound_speed_m_s"],
        )
        for kind in ("contrast", "resolution")
    }
    series = [
        ("Lateral FWHM [mm]", by_kind["resolution"],
         lambda row: row["metrics"]["median_lateral_fwhm_mm"]),
        ("Axial FWHM [mm]", by_kind["resolution"],
         lambda row: row["metrics"]["median_axial_fwhm_mm"]),
        ("Position RMSE [mm]", by_kind["resolution"],
         lambda row: row["metrics"]["position_rmse_mm"]),
        ("Shallow cyst gCNR", by_kind["contrast"],
         lambda row: row["metrics"]["cysts"]["shallow_cyst"]["generalized_cnr"]),
        ("Deep cyst gCNR", by_kind["contrast"],
         lambda row: row["metrics"]["cysts"]["deep_cyst"]["generalized_cnr"]),
        ("Embedded-reference SSIM", by_kind["resolution"],
         lambda row: row["embedded_reference_similarity"]["ssim"]),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), layout="constrained")
    for axis, (label, rows, value) in zip(axes.ravel(), series, strict=True):
        axis.plot([row["sound_speed_m_s"] for row in rows], [value(row) for row in rows],
                  "o-", color="#248c9e")
        axis.axvline(1540, color="#8c94a4", linestyle=":", label="Metadata 1540 m/s")
        axis.set(xlabel="Assumed sound speed [m/s]", ylabel=label)
        axis.grid(alpha=0.25)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Measured PICMUS phantoms · cubic interpolation · 11 angles")
    fig.savefig(output, dpi=170)
    plt.close(fig)


def _summary(row):
    if row["kind"] == "resolution":
        metrics = row["metrics"]
        return (f"lateral {metrics['median_lateral_fwhm_mm']:.4f} mm; "
                f"axial {metrics['median_axial_fwhm_mm']:.4f} mm")
    cysts = row["metrics"]["cysts"]
    return (f"shallow/deep gCNR {cysts['shallow_cyst']['generalized_cnr']:.4f} / "
            f"{cysts['deep_cyst']['generalized_cnr']:.4f}")


def run_interpolation_study(data_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "contrast": data_dir / "PICMUS_experiment_contrast_speckle.uff",
        "resolution": data_dir / "PICMUS_experiment_resolution_distortion.uff",
    }
    acquisitions = {kind: load_picmus_uff(path) for kind, path in paths.items()}
    caches = {kind: prepare_analytic_channel_cache(acquisition, 8)
              for kind, acquisition in acquisitions.items()}
    report = _base_report("Measured-phantom delay interpolation and sound-speed sensitivity")
    report.update({
        "datasets": [_provenance(paths[kind], acquisitions[kind]) for kind in paths],
        "settings": {
            "analytic": True, "f_number": 1.7, "stride": 2,
            "angle_batch_size": 8, "cache_batch_size": 8,
            "sound_speeds_m_s": list(SOUND_SPEEDS_M_S),
        },
        "cache": {
            kind: {"size_mib": cache.size_mib,
                   "preparation_seconds": cache.preparation_seconds}
            for kind, cache in caches.items()
        },
        "interpolation_definition": (
            "Linear uses two adjacent samples. Cubic uses four adjacent samples with the "
            "Catmull-Rom cubic convolution formula. Cubic excludes the first/last extra "
            "boundary sample required by its support."
        ),
        "reference_limit": (
            "Embedded UFF images are same-acquisition algorithmic references, not anatomical "
            "ground truth. Nominal phantom target coordinates are approximate. No setting is "
            "selected or promoted from this sensitivity study; defaults remain unchanged."
        ),
        "timing_limit": (
            "Per-call wall durations are retained only for run traceability. Execution order, "
            "JIT state and warmup are not controlled, so they are not a performance comparison."
        ),
        "interpolation_records": [],
        "sound_speed_records": [],
    })

    for kind, acquisition in acquisitions.items():
        panels = []
        point_sets = []
        for count in (11, acquisition.transmit_angles_rad.size):
            for interpolation in ("linear", "cubic"):
                result, row = _reconstruct(
                    acquisition, caches[kind], kind, interpolation,
                    acquisition.sound_speed_m_s, count,
                )
                report["interpolation_records"].append(row)
                panels.append((f"{interpolation.capitalize()} · {count} angles", result.bmode_db))
                if kind == "resolution":
                    point_sets.append(row["metrics"]["points"])
                print(f"{kind}, {count} angles, {interpolation}: {_summary(row)}", flush=True)
        _save_panels(
            panels, result.x_axis_m, result.z_axis_m,
            output_dir / f"{kind}_interpolation.png",
            "Measured phantom · delay interpolation comparison", kind,
            point_sets if kind == "resolution" else None,
        )

    for speed in SOUND_SPEEDS_M_S:
        for kind, acquisition in acquisitions.items():
            _, row = _reconstruct(
                acquisition, caches[kind], kind, "cubic", speed, 11,
            )
            report["sound_speed_records"].append(row)
            print(f"{kind}, {speed:.0f} m/s: {_summary(row)}", flush=True)

    _plot_sound_speed(report["sound_speed_records"], output_dir / "sound_speed_sensitivity.png")
    _save_report(finite_json(report), output_dir)
    return finite_json(report)


def _save_report(report, output_dir):
    lines = [
        "# Delay interpolation and sound-speed sensitivity", "",
        report["interpolation_definition"], "", report["reference_limit"], "",
        "## Linear versus cubic delay interpolation", "",
        "| Phantom | Angles | Method | Physical measurement | Reference SSIM |",
        "|---|---:|---|---|---:|",
    ]
    for row in report["interpolation_records"]:
        lines.append(
            f"| {row['kind']} | {row['angle_count']} | {row['interpolation']} | "
            f"{_summary(row)} | {row['embedded_reference_similarity']['ssim']:.4f} |"
        )
    lines += [
        "", ("[Contrast images](contrast_interpolation.png) · "
             "[Resolution images](resolution_interpolation.png)"), "",
        "## Assumed sound-speed sweep", "",
        "Cubic interpolation, 11 angles, F/1.7 and stride 2 are fixed.", "",
        ("| Speed m/s | Lateral / axial FWHM mm | Position RMSE mm | "
         "Shallow / deep gCNR | Resolution / contrast reference SSIM |"),
        "|---:|---:|---:|---:|---:|",
    ]
    for speed in SOUND_SPEEDS_M_S:
        contrast = next(row for row in report["sound_speed_records"]
                        if row["kind"] == "contrast" and row["sound_speed_m_s"] == speed)
        resolution = next(row for row in report["sound_speed_records"]
                          if row["kind"] == "resolution" and row["sound_speed_m_s"] == speed)
        rm = resolution["metrics"]
        cysts = contrast["metrics"]["cysts"]
        lines.append(
            f"| {speed:.0f} | {rm['median_lateral_fwhm_mm']:.4f} / "
            f"{rm['median_axial_fwhm_mm']:.4f} | {rm['position_rmse_mm']:.4f} | "
            f"{cysts['shallow_cyst']['generalized_cnr']:.4f} / "
            f"{cysts['deep_cyst']['generalized_cnr']:.4f} | "
            f"{resolution['embedded_reference_similarity']['ssim']:.4f} / "
            f"{contrast['embedded_reference_similarity']['ssim']:.4f} |"
        )
    lines += [
        "", "![Sound-speed sensitivity](sound_speed_sensitivity.png)", "",
        "[Full per-target, cyst, timing, cache and provenance records](metrics.json)", "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "metrics.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("artifacts/interpolation_study"))
    args = parser.parse_args()
    run_interpolation_study(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
