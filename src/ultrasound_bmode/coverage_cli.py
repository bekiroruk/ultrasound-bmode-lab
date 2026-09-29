"""Monte Carlo coverage audit with known Rayleigh envelope population metrics."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .metrics import circular_mask
from .roi import LumenRoi
from .spatial_roi import METRICS, _positive_integer, paired_spatial_bootstrap


def rayleigh_truth(target_scale=0.5, background_scale=1.0):
    if not 0 < target_scale < background_scale:
        raise ValueError("scales must satisfy 0 < target < background")
    a, b = target_scale, background_scale
    crossing_squared = 4 * math.log(b / a) / (1/a**2 - 1/b**2)
    return {
        "contrast_db": 20 * math.log10(a/b),
        "cnr": math.sqrt(math.pi / 2) * (b-a) / math.sqrt((2-math.pi/2)*(a*a+b*b)),
        "generalized_cnr": math.exp(-crossing_squared/(2*b*b))
        - math.exp(-crossing_squared/(2*a*a)),
    }


def draw_envelope(rng, correlated=False):
    axis = np.arange(64) * 0.25e-3
    roi = LumenRoi(8e-3, 8e-3, 2e-3)
    if correlated:
        # IID 4x4 constant tiles offset by two pixels from the evaluation partition.
        field = rng.rayleigh(size=(17, 17)).repeat(4, axis=0).repeat(4, axis=1)[2:66, 2:66]
    else:
        field = rng.rayleigh(size=(64, 64))
    target = circular_mask(axis, axis, roi.center_x_m, roi.center_z_m, roi.radius_m)
    field[target] *= 0.5
    return field, axis, roi


def wilson_interval(successes, total):
    if total < 1 or not 0 <= successes <= total:
        raise ValueError("invalid binomial counts")
    p, z = successes / total, 1.959963984540054
    center = (p + z*z/(2*total)) / (1 + z*z/total)
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total**2)) / (1 + z*z/total)
    return [max(0, center-half), min(1, center+half)]


def summarize_coverage(records, truth):
    output = []
    for scenario in ("iid", "offset_correlated_tiles"):
        for block in (1, 4, 8):
            rows = [r for r in records if r["scenario"] == scenario and r["block"] == block]
            for metric in METRICS:
                intervals = [row["metrics"][metric]["percentile95"] for row in rows]
                covered = sum(lo <= truth[metric] <= hi for lo, hi in intervals)
                output.append({
                    "scenario": scenario, "block": block, "metric": metric, "trials": len(rows),
                    "covered": covered, "coverage": covered / len(rows),
                    "coverage_wilson95": wilson_interval(covered, len(rows)),
                    "mean_width": float(np.mean([hi-lo for lo, hi in intervals])),
                    "bias": float(np.mean([row["metrics"][metric]["estimate"]
                                          for row in rows]) - truth[metric]),
                })
    return output


def run_coverage(output_dir, trials=200, samples=300, seed=20260929):
    _positive_integer(trials, "trials", 2)
    _positive_integer(samples, "samples", 20)
    _positive_integer(seed, "seed", 0)
    truth = rayleigh_truth()
    report = {
        "study": "Controlled Monte Carlo coverage audit",
        "settings": {"trials_per_scenario": trials, "bootstrap_samples": samples, "seed": seed,
                     "block_sizes": [1, 4, 8], "target_rayleigh_scale": 0.5,
                     "background_rayleigh_scale": 1.0},
        "truth": truth,
        "scope": (
            "Synthetic envelopes with exactly known marginal Rayleigh distributions, not RF "
            "acquisitions. IID pixels and 4x4 constant tiles offset by two pixels. Fixed mask "
            "and origin. Each trial is independently generated; same field across block sizes. "
            "Coverage means interval contains the population metric. Continuous gCNR truth "
            "is compared to the existing adaptive 64-bin estimator, retaining histogram bias."
        ),
        "limitations": (
            "Finite Monte Carlo precision is quantified with Wilson intervals. No clinical "
            "coverage guarantee or automatic correction factor. Tile model is not a tissue "
            "model; ROI selection, paired changes and other correlation structures are untested. "
            "No block size is selected from these trials."
        ),
        "records": [],
    }
    streams = np.random.SeedSequence(seed).spawn(2 * trials)
    for case_index, scenario in enumerate(("iid", "offset_correlated_tiles")):
        for trial in range(trials):
            field_seed, resampling_seed = streams[case_index*trials + trial].spawn(2)
            field, axis, roi = draw_envelope(np.random.default_rng(field_seed), case_index == 1)
            bootstrap_seed = int(resampling_seed.generate_state(1)[0])
            for block in (1, 4, 8):
                result = paired_spatial_bootstrap(
                    {"envelope": field}, axis, axis, roi, block_size=block,
                    samples=samples, seed=bootstrap_seed)
                report["records"].append({
                    "scenario": scenario, "trial": trial, "block": block,
                    "bootstrap_seed": bootstrap_seed, "metrics": result["images"]["envelope"],
                    "rejected_draws": result["rejected_insufficient_support_draws"],
                })
            if (trial + 1) % 20 == 0:
                print(f"{scenario}: {trial + 1}/{trials} fields", flush=True)
    report["summaries"] = summarize_coverage(report["records"], truth)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n",
                                            encoding="utf-8")
    lines = ["# Controlled uncertainty coverage audit", "", report["scope"], "",
             report["limitations"], "", f"{trials} fields/scenario; {samples} resamples/interval.",
             "", "| Scenario | Block | Metric | Coverage | Wilson 95% | Bias |",
             "|---|---:|---|---:|---|---:|"]
    for row in report["summaries"]:
        lo, hi = row["coverage_wilson95"]
        lines.append(f"| {row['scenario']} | {row['block']} | {row['metric']} | "
                     f"{row['coverage']:.3f} | [{lo:.3f}, {hi:.3f}] | {row['bias']:+.4f} |")
    lines += ["", "Nominal 95% percentile intervals are not automatically 95%-coverage intervals.",
              "The displayed coverage is an observed frequency, not a pass/fail certification.",
              "", "![Coverage audit](coverage.png)", "", "[Raw trials](metrics.json)", ""]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    for axis, metric in zip(axes, METRICS, strict=True):
        for scenario in ("iid", "offset_correlated_tiles"):
            rows = [row for row in report["summaries"]
                    if row["scenario"] == scenario and row["metric"] == metric]
            axis.plot([r["block"] for r in rows], [r["coverage"] for r in rows],
                      "o-", label=scenario)
        axis.axhline(0.95, color="gray", linestyle="--")
        axis.set(title=metric, xlabel="Block side [pixels]", ylabel="Observed coverage",
                 ylim=(0, 1.02), xticks=[1, 4, 8])
    axes[0].legend(fontsize=8)
    fig.savefig(output_dir / "coverage.png", dpi=160)
    plt.close(fig)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/coverage"))
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--samples", type=int, default=300)
    args = parser.parse_args()
    run_coverage(args.output_dir, args.trials, args.samples)


if __name__ == "__main__":
    main()
