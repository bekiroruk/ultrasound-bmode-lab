"""Controlled coverage study of a Rayleigh-model gCNR estimator.

This estimates population gCNR only under two Rayleigh envelope laws. It does
not replace the distribution-free histogram metric used for measured images.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .coverage_cli import draw_envelope, rayleigh_truth, wilson_interval
from .metrics import circular_mask
from .spatial_roi import _positive_integer

CASES = (
    ("iid_rayleigh", 1, 0),
    ("iid_rayleigh", 8, 0),
    ("offset_correlated_rayleigh", 1, 0),
    ("offset_correlated_rayleigh", 4, 2),
    ("offset_correlated_rayleigh", 8, 0),
    ("offset_correlated_rayleigh", 8, 2),
    ("iid_lognormal_stress", 1, 0),
)


def rayleigh_overlap_gcnr(target_scale, background_scale):
    """Total variation between Rayleigh laws, including equal/reversed scales."""
    a = np.asarray(target_scale, dtype=float)
    b = np.asarray(background_scale, dtype=float)
    if np.any(~np.isfinite(a)) or np.any(~np.isfinite(b)) or np.any(a <= 0) or np.any(b <= 0):
        raise ValueError("Rayleigh scales must be finite and positive")
    ratio = np.log(b/a)
    denominator = 1/a**2 - 1/b**2
    crossing_squared = np.divide(4*ratio, denominator, out=np.zeros_like(ratio),
                                 where=denominator != 0)
    gcnr = np.abs(np.exp(-crossing_squared/(2*b**2))
                  - np.exp(-crossing_squared/(2*a**2)))
    return float(gcnr) if gcnr.ndim == 0 else gcnr


def rayleigh_mle_gcnr(target, background):
    """Fit zero-location Rayleigh scales by sqrt(mean(envelope**2)/2)."""
    target, background = np.asarray(target, dtype=float), np.asarray(background, dtype=float)
    if (not target.size or not background.size or not np.isfinite(target).all()
            or not np.isfinite(background).all() or np.any(target < 0)
            or np.any(background < 0)):
        raise ValueError("expected finite, nonnegative and nonempty envelope samples")
    a, b = np.sqrt(np.mean(target**2)/2), np.sqrt(np.mean(background**2)/2)
    return rayleigh_overlap_gcnr(a, b)


def _region_tiles(field, axis, roi, side, origin):
    target = circular_mask(axis, axis, roi.center_x_m, roi.center_z_m, roi.radius_m)
    background = circular_mask(axis, axis, roi.center_x_m, roi.center_z_m,
                               roi.radius_m+3e-3)
    background &= ~circular_mask(axis, axis, roi.center_x_m, roi.center_z_m,
                                 roi.radius_m+1e-3)
    union = target | background
    rows, columns = np.nonzero(union)
    pair = np.column_stack(((rows-origin)//side, (columns-origin)//side))
    _, labels = np.unique(pair, axis=0, return_inverse=True)
    is_target = target[union]
    if min(np.unique(labels[is_target]).size, np.unique(labels[~is_target]).size) < 4:
        raise ValueError("too few occupied tiles in one region")
    values = field[union]
    tiles = int(labels.max()+1)
    return (
        rayleigh_mle_gcnr(values[is_target], values[~is_target]),
        np.bincount(labels[is_target], minlength=tiles),
        np.bincount(labels[~is_target], minlength=tiles),
        np.bincount(labels[is_target], weights=values[is_target]**2, minlength=tiles),
        np.bincount(labels[~is_target], weights=values[~is_target]**2, minlength=tiles),
        float(np.std(values[is_target])/np.mean(values[is_target])),
        float(np.std(values[~is_target])/np.mean(values[~is_target])),
    )


def tile_interval(field, axis, roi, *, block_size, origin, samples, seed):
    """Occupied-tile percentile interval for Rayleigh-model gCNR."""
    _positive_integer(block_size, "block_size")
    _positive_integer(origin, "origin", 0)
    _positive_integer(samples, "samples", 20)
    _positive_integer(seed, "seed", 0)
    if origin >= block_size:
        raise ValueError("origin must be below block size")
    if field.shape != (axis.size, axis.size) or not np.isfinite(field).all() or np.any(field < 0):
        raise ValueError("field must be finite, nonnegative and match the square grid")
    estimate, nt, nb, st, sb, cvt, cvb = _region_tiles(field, axis, roi, block_size, origin)
    count = nt.size
    rng = np.random.default_rng(seed)
    result = []
    rejected = 0
    while len(result) < samples:
        batch = rng.multinomial(count, np.full(count, 1/count),
                                size=samples-len(result))
        target_n, background_n = batch@nt, batch@nb
        valid = (target_n >= 2) & (background_n >= 2)
        rejected += int((~valid).sum())
        if rejected > 20*samples:
            raise ValueError("too many unsupported bootstrap draws")
        if not valid.any():
            continue
        batch = batch[valid]
        a = np.sqrt((batch@st)/(2*target_n[valid]))
        b = np.sqrt((batch@sb)/(2*background_n[valid]))
        result.extend(np.asarray(rayleigh_overlap_gcnr(a, b)).tolist())
    lower, upper = np.percentile(result[:samples], [2.5, 97.5])
    return {
        "estimate": estimate, "percentile95": [float(lower), float(upper)],
        "basic95": [float(max(0, 2*estimate-upper)),
                    float(min(1, 2*estimate-lower))],
        "bootstrap_mean_minus_estimate": float(np.mean(result[:samples])-estimate),
        "occupied_blocks": count, "target_blocks": int(np.count_nonzero(nt)),
        "background_blocks": int(np.count_nonzero(nb)),
        "rejected_draws": rejected, "target_cv": cvt, "background_cv": cvb,
    }


def _draw_field(rng, scenario):
    if scenario == "iid_lognormal_stress":
        _, axis, roi = draw_envelope(np.random.default_rng(0))
        field = rng.lognormal(mean=0, sigma=0.7, size=(64, 64))
        field[circular_mask(axis, axis, roi.center_x_m, roi.center_z_m,
                            roi.radius_m)] *= 0.5
        return field, axis, roi
    return draw_envelope(rng, correlated=scenario == "offset_correlated_rayleigh")


def run_study(output_dir, trials=200, samples=300, seed=20261001):
    """Evaluate fixed configurations on independent Monte Carlo fields, no tuning."""
    _positive_integer(trials, "trials", 2)
    _positive_integer(samples, "samples", 20)
    _positive_integer(seed, "seed", 0)
    rayleigh_value = rayleigh_truth()["generalized_cnr"]
    # Equal-variance normal laws in log amplitude, means separated by ln(2).
    lognormal_value = math.erf(math.log(2)/(2*math.sqrt(2)*0.7))
    truths = {"iid_rayleigh": rayleigh_value,
              "offset_correlated_rayleigh": rayleigh_value,
              "iid_lognormal_stress": lognormal_value}
    source = "https://lab.vanderbilt.edu/beamlab/wp-content/uploads/sites/191/2024/04/schlunk_2023_gcnr.pdf"
    report = {
        "study": "Model-assisted gCNR interval coverage; controlled Monte Carlo",
        "sources": [source],
        "settings": {"trials_per_scenario": trials, "bootstrap_samples": samples, "seed": seed,
                     "cases": [{"scenario": s, "block_size": b, "block_origin": [o, o]}
                               for s, b, o in CASES],
                     "rayleigh_target_scale": 0.5, "rayleigh_background_scale": 1.0,
                     "lognormal_sigma": 0.7},
        "truth": truths, "records": [], "summaries": [],
        "scope": (
            "Synthetic envelopes, not RF or patient data. Rayleigh MLE scales and exact "
            "two-Rayleigh density overlap; fixed ROI. Pixel IID, offset 4x4 constant tiles, "
            "and misspecified IID lognormal stress. Block origins 0 and 2 were fixed from "
            "the generator geometry, never selected from results. Independent random fields "
            "across scenarios; same field across block options. Percentile resampling treats "
            "occupied 1x1, 4x4 or 8x8 tiles as units and preserves partial ROI masks."
        ),
        "limitations": (
            "A Rayleigh model is not established for human tissue, adaptive beamformers "
            "or all phantoms. Better coverage on its generating model cannot validate "
            "intervals for measured RF. Aligned blocks require knowledge of correlation "
            "geometry; this experiment does not estimate it. The basic interval reflects "
            "bootstrap quantiles around the point estimate and is evaluated on a fresh "
            "seed after the initial percentile runs. Lognormal stress uses a known "
            "non-Rayleigh population and deliberately tests model failure. Finite Monte "
            "Carlo uncertainty is summarized by Wilson intervals; no calibration on "
            "these evaluation trials, no automatic replacement of the 64-bin metric."
        ),
    }
    streams = np.random.SeedSequence(seed).spawn(3*trials)
    for case_index, scenario in enumerate(truths):
        configs = [(b, o) for s, b, o in CASES if s == scenario]
        for trial in range(trials):
            field_seed, resampling_seed = streams[case_index*trials+trial].spawn(2)
            field, axis, roi = _draw_field(np.random.default_rng(field_seed), scenario)
            bootstrap_seed = int(resampling_seed.generate_state(1)[0])
            for block, origin in configs:
                result = tile_interval(field, axis, roi, block_size=block, origin=origin,
                                       samples=samples, seed=bootstrap_seed)
                report["records"].append({
                    "scenario": scenario, "trial": trial, "block_size": block,
                    "origin": origin, "bootstrap_seed": bootstrap_seed, **result,
                })
        print(f"{scenario}: {trials} independent fields", flush=True)
    for scenario, block, origin in CASES:
        rows = [row for row in report["records"] if row["scenario"] == scenario
                and row["block_size"] == block and row["origin"] == origin]
        truth = truths[scenario]
        covered = sum(row["percentile95"][0] <= truth <= row["percentile95"][1]
                      for row in rows)
        basic_covered = sum(row["basic95"][0] <= truth <= row["basic95"][1]
                            for row in rows)
        report["summaries"].append({
            "scenario": scenario, "block_size": block, "origin": origin,
            "covered": covered, "trials": trials, "coverage": covered/trials,
            "wilson95": wilson_interval(covered, trials),
            "basic_covered": basic_covered, "basic_coverage": basic_covered/trials,
            "basic_wilson95": wilson_interval(basic_covered, trials),
            "mean_estimate": float(np.mean([row["estimate"] for row in rows])),
            "bias": float(np.mean([row["estimate"] for row in rows])-truth),
            "mean_width": float(np.mean([row["percentile95"][1]-row["percentile95"][0]
                                        for row in rows])),
            "mean_target_cv": float(np.mean([row["target_cv"] for row in rows])),
            "mean_background_cv": float(np.mean([row["background_cv"] for row in rows])),
        })
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n",
                                            encoding="utf-8")
    lines = ["# Rayleigh-model gCNR coverage stress test", "", report["scope"], "",
             report["limitations"], "",
             f"{trials} independent fields/scenario; {samples} resamples/interval.",
             f"Rayleigh truth: {rayleigh_value:.6f}; lognormal truth: {lognormal_value:.6f}.",
             f"Source: [Schlunk & Byram (2023)]({source}).", "",
             "| Scenario | Block | Origin | Percentile | Basic | Bias | Width |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in report["summaries"]:
        lines.append(f"| {row['scenario']} | {row['block_size']} | {row['origin']} | "
                     f"{row['coverage']:.3f} | {row['basic_coverage']:.3f} | "
                     f"{row['bias']:+.4f} | {row['mean_width']:.4f} |")
    lines += ["", ("Wilson 95% intervals for both observed coverage frequencies are "
                   "stored in metrics.json."), "",
              ("This is a conditional model diagnostic, not a general solution for "
                   "measured ultrasound or calibrated clinical intervals."),
              "", "![Coverage by scenario and block](coverage.png)", "",
              "[All independent trials](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
    names = {"iid_rayleigh": "IID Rayleigh",
             "offset_correlated_rayleigh": "4×4 tiles",
             "iid_lognormal_stress": "IID lognormal"}
    labels = [f"{names[r['scenario']]}\n{r['block_size']} px"
              + (" aligned" if r["origin"] == 2 else "")
              for r in report["summaries"]]
    positions = np.arange(len(labels))
    ax.bar(positions-0.18, [r["coverage"] for r in report["summaries"]], width=0.36,
           color=["#417e9c" if "rayleigh" in r["scenario"] else "#b67760"
                  for r in report["summaries"]], label="Percentile")
    ax.bar(positions+0.18, [r["basic_coverage"] for r in report["summaries"]],
           width=0.36, color="#83b986", label="Basic")
    ax.axhline(0.95, color="black", linestyle="--", label="Nominal 0.95")
    ax.set(ylabel="Observed truth coverage", ylim=(0, 1.05),
           title="Conditional coverage on independent synthetic fields")
    ax.set_xticks(positions, labels)
    ax.tick_params(axis="x", labelsize=8)
    ax.legend()
    fig.savefig(output_dir / "coverage.png", dpi=160)
    plt.close(fig)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/rayleigh_coverage"))
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20261001)
    args = parser.parse_args()
    run_study(args.output_dir, args.trials, args.samples, args.seed)


if __name__ == "__main__":
    main()
