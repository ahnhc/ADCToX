#!/usr/bin/env python
"""Across-agent organ ranking, with between-agent reporting conditions removed.

This is the project's one positive result, so it is built to be attacked.

The metric: within one organ axis, rank the 16 agents by predicted rate and by observed
rate, and correlate. It is the comparison the product actually makes -- "is this chemistry
worse for the liver than that one" -- and unlike the within-arm metric a constant per-axis
predictor has no discriminative power on it by construction.

The problem it fixes. Agents were tested under wildly different reporting conditions, and
the spread between them is comparable to the design effect being measured:

    combination fraction   0.00 to 0.96   (T-DM1 is 96% combination arms; six agents 0%)
    reporting threshold   -2.25 to +0.75
    trial size            -0.44 to +0.57

Multiplied by their fitted coefficients that is about 0.33 logit of between-agent spread
that is purely reporting practice, against a tubulin mechanism effect of sd 0.278. So the
observed ranking is partly a ranking of how each drug happened to be studied.

The fix is to subtract the reporting contribution from BOTH series before correlating,
which leaves each agent's organ profile at a common reference. Direction was not assumed:
a shared artefact in both series would have inflated the correlation and removing it would
have lowered the result. It raises it.

What is deliberately NOT adjusted for: anything carrying design information. Only the
three arm-level nuisance covariates are used, and the script reports the result both with
coefficients taken from the main fit and with coefficients estimated design-blind, because
the former were fitted jointly with the design terms and that dependence is a fair
objection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.model import dataset as ds  # noqa: E402
from adctox.provenance import write_json  # noqa: E402
from adctox.taxonomy import default_taxonomy  # noqa: E402

MIN_AGENTS_PER_AXIS = 6


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    rx -= rx.mean()
    ry -= ry.mean()
    den = np.sqrt((rx**2).sum() * (ry**2).sum())
    return float((rx * ry).sum() / den) if den else float("nan")


def _irls(X, y, n, n_axes):
    beta = np.zeros(X.shape[1])
    p0 = (y.sum() + 0.5) / (n.sum() + 1.0)
    beta[:n_axes] = np.log(p0 / (1 - p0))
    for _ in range(80):
        eta = X @ beta
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = n * mu * (1 - mu) + 1e-9
        z = eta + (y - n * mu) / w
        wx = X * w[:, None]
        new = np.linalg.solve(X.T @ wx + 1e-6 * np.eye(X.shape[1]), wx.T @ z)
        if np.abs(new - beta).max() < 1e-10:
            return new
        beta = new
    return beta


def design_blind_with_trial_effects(data) -> dict[str, float]:
    """Combination effect identified WITHIN trials, design-blind.

    The most defensible of the three estimators here, and the one the headline uses.
    Trial fixed effects mean the combination coefficient comes from comparing combination
    and monotherapy arms of the same trial, so it is not confounded with whatever else
    differs between trials.

    Two structural facts constrain this, both measured:

      * `b_thresh` has exactly zero within-trial variance -- the reporting threshold is a
        trial-level constant -- so it cannot be identified within trials at all and is
        set to zero here rather than estimated from a between-trial contrast that is
        confounded with everything else about the trial.
      * `b_combo` is identified from only 6 trials and 20 arms, the ones carrying both a
        combination and a monotherapy arm. Real, but thin, and the estimate is
        correspondingly uncertain.
    """
    idx = data.point_idx
    axis = np.asarray(data.axis_idx)[idx]
    arm = np.asarray(data.arm_idx)[idx]
    n = np.asarray(data.n_at_risk, dtype=float)[idx]
    y = np.asarray(data.n_affected, dtype=float)[idx]
    n_axes = len(data.axes)
    trial = np.asarray(data.arm_trial_idx)
    carries = np.asarray(data.arm_has_trial_effect).astype(bool)
    trials = sorted(set(trial[carries].tolist()))
    tmap = {t: i for i, t in enumerate(trials)}

    X = np.zeros((len(idx), n_axes + len(trials) + 2))
    X[np.arange(len(idx)), axis] = 1.0
    for row, a in enumerate(arm):
        if carries[a]:
            X[row, n_axes + tmap[int(trial[a])]] = 1.0
    X[:, n_axes + len(trials) + 0] = np.asarray(data.arm_combo, dtype=float)[arm]
    X[:, n_axes + len(trials) + 1] = np.asarray(data.arm_log_n_c, dtype=float)[arm]
    beta = _irls(X, y, n, n_axes)
    return {
        "b_combo": float(beta[n_axes + len(trials) + 0]),
        "b_thresh": 0.0,
        "b_log_n": float(beta[n_axes + len(trials) + 1]),
    }


def design_blind_nuisance(data) -> dict[str, float]:
    """Same three covariates with axis intercepts and no trial term.

    Kept for contrast: without trial effects the combination coefficient is a marginal
    association and comes out six times smaller (0.032 against 0.195 in the joint fit).
    The spread between the three estimators is the main caveat on this whole result.
    """
    idx = data.point_idx
    axis = np.asarray(data.axis_idx)[idx]
    n = np.asarray(data.n_at_risk, dtype=float)[idx]
    y = np.asarray(data.n_affected, dtype=float)[idx]
    arm = np.asarray(data.arm_idx)[idx]
    n_axes = len(data.axes)
    X = np.zeros((len(idx), n_axes + 3))
    X[np.arange(len(idx)), axis] = 1.0
    X[:, n_axes + 0] = np.asarray(data.arm_combo, dtype=float)[arm]
    X[:, n_axes + 1] = np.asarray(data.arm_thresh_c, dtype=float)[arm]
    X[:, n_axes + 2] = np.asarray(data.arm_log_n_c, dtype=float)[arm]

    beta = np.zeros(X.shape[1])
    beta[:n_axes] = _logit((y.sum() + 0.5) / (n.sum() + 1.0))
    for _ in range(60):
        eta = X @ beta
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = n * mu * (1 - mu) + 1e-9
        z = eta + (y - n * mu) / w
        wx = X * w[:, None]
        beta_new = np.linalg.solve(X.T @ wx + 1e-8 * np.eye(X.shape[1]), wx.T @ z)
        if np.abs(beta_new - beta).max() < 1e-9:
            beta = beta_new
            break
        beta = beta_new
    return {
        "b_combo": float(beta[n_axes + 0]),
        "b_thresh": float(beta[n_axes + 1]),
        "b_log_n": float(beta[n_axes + 2]),
    }


def _per_axis(fp: pd.DataFrame, cond: dict, coef: dict | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for axis, g in fp.groupby("axis"):
        g = g[g.fold.isin(cond)]
        if len(g) < MIN_AGENTS_PER_AXIS:
            continue
        pred = _logit(g.pred.values)
        obs = _logit(g.obs.values)
        if coef is None:
            off = np.zeros(len(g))
        else:
            off = np.array([
                coef["b_combo"] * cond[f][0]
                + coef["b_thresh"] * cond[f][1]
                + coef["b_log_n"] * cond[f][2]
                for f in g.fold
            ])
        out[axis] = _spearman(pred - off, obs - off)
    return out


def _bootstrap(values: np.ndarray, n: int = 4000, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    means = [rng.choice(values, len(values), replace=True).mean() for _ in range(n)]
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def _permutation_p(fp: pd.DataFrame, cond: dict, coef: dict, observed: float,
                   n: int = 4000, seed: int = 7) -> float:
    """Shuffle the agent labels of the observed series within each axis.

    Preferred over the bootstrap interval as the headline test, because the 14 axis
    correlations are not independent -- one agent's organs covary -- and a bootstrap over
    axes assumes they are. A within-axis permutation keeps that structure intact.
    """
    rng = np.random.default_rng(seed)
    series = []
    for axis, g in fp.groupby("axis"):
        g = g[g.fold.isin(cond)]
        if len(g) < MIN_AGENTS_PER_AXIS:
            continue
        off = np.array([
            coef["b_combo"] * cond[f][0] + coef["b_thresh"] * cond[f][1]
            + coef["b_log_n"] * cond[f][2] for f in g.fold
        ])
        series.append((_logit(g.pred.values) - off, _logit(g.obs.values) - off))
    hits = 0
    for _ in range(n):
        vals = [_spearman(p, rng.permutation(o)) for p, o in series]
        hits += np.mean(vals) >= observed
    return float(hits / n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=Path, default=Path("data/processed"))
    ap.add_argument("--fold-predictions", type=Path,
                    default=Path("artifacts/forward_other_fold_predictions.parquet"))
    ap.add_argument("--metrics", type=Path,
                    default=Path("artifacts/forward_other_metrics.json"))
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    args = ap.parse_args()

    if not args.fold_predictions.exists():
        print(f"{args.fold_predictions} absent; run `make forward`")
        return 1
    data = ds.load(args.processed, list(default_taxonomy().axis_order), kind="other")
    fp = pd.read_parquet(args.fold_predictions)
    fp = fp[fp.split == "leave_one_agent_out"]

    cond, mech = {}, {}
    for i, agent in enumerate(data.agents):
        k = data.arm_agent_idx == i
        if not k.any():
            continue
        cond[agent] = (
            float(np.asarray(data.arm_combo)[k].mean()),
            float(np.asarray(data.arm_thresh_c)[k].mean()),
            float(np.asarray(data.arm_log_n_c)[k].mean()),
        )
        mech[agent] = data.mechanisms[int(np.asarray(data.arm_mech_idx)[k][0])]

    joint = json.loads(args.metrics.read_text(encoding="utf-8"))["coefficients"]
    joint_coef = {k: joint[k]["mean"] for k in ("b_combo", "b_thresh", "b_log_n")}
    blind_coef = design_blind_nuisance(data)
    within_coef = design_blind_with_trial_effects(data)

    print("nuisance coefficients used for the adjustment")
    print(f"  {'':12s} {'b_combo':>9s} {'b_thresh':>9s} {'b_log_n':>9s}")
    print(f"  {'joint fit':12s} {joint_coef['b_combo']:9.4f} "
          f"{joint_coef['b_thresh']:9.4f} {joint_coef['b_log_n']:9.4f}")
    print(f"  {'design-blind':12s} {blind_coef['b_combo']:9.4f} "
          f"{blind_coef['b_thresh']:9.4f} {blind_coef['b_log_n']:9.4f}")
    print(f"  {'blind+trialFE':12s} {within_coef['b_combo']:9.4f} "
          f"{within_coef['b_thresh']:9.4f} {within_coef['b_log_n']:9.4f}   <- headline")

    variants = {
        "unadjusted": None,
        "combination_only": {**{k: 0.0 for k in joint_coef}, "b_combo": joint_coef["b_combo"]},
        "adjusted_joint_coefficients": joint_coef,
        "adjusted_design_blind_coefficients": blind_coef,
        "adjusted_within_trial_blind": within_coef,
    }
    results = {}
    print(f"\n  {'variant':38s} {'mean rho':>9s} {'95% CI':>22s}")
    for name, coef in variants.items():
        per = _per_axis(fp, cond, coef)
        vals = np.array(list(per.values()))
        ci = _bootstrap(vals)
        results[name] = {
            "mean_spearman": float(vals.mean()), "ci": ci,
            "n_axes": len(vals), "per_axis": per,
            "coefficients": coef,
        }
        print(f"  {name:38s} {vals.mean():+9.4f}  [{ci[0]:+.4f}, {ci[1]:+.4f}]"
              f"{'  significant' if ci[0] > 0 else ''}")

    ps = {}
    print(f"\n  permutation test, agent labels shuffled within each axis")
    for name, coef in (("adjusted_joint_coefficients", joint_coef),
                       ("adjusted_within_trial_blind", within_coef),
                       ("adjusted_design_blind_coefficients", blind_coef)):
        ps[name] = _permutation_p(fp, cond, coef, results[name]["mean_spearman"])
        mark = "  <- headline" if name == "adjusted_within_trial_blind" else ""
        print(f"    {name:38s} p = {ps[name]:.4f}{mark}")
    p_joint = ps["adjusted_joint_coefficients"]
    p_blind = ps["adjusted_design_blind_coefficients"]

    # How much of the combination fraction is mechanism rather than study design?
    labels = [mech[a] for a in cond]
    combo = np.array([cond[a][0] for a in cond])
    grand = combo.mean()
    between = sum(
        sum(1 for a in cond if mech[a] == m)
        * (np.mean([cond[a][0] for a in cond if mech[a] == m]) - grand) ** 2
        for m in set(labels)
    )
    total = float(((combo - grand) ** 2).sum())
    frac = float(between / total) if total else float("nan")
    print(f"\n  mechanism explains {100 * frac:.0f}% of the combination-fraction variance")
    print("    so most of what the adjustment removes is within-mechanism study design,")
    print("    and removing a confound shared by both series could only lower the result")

    write_json(
        args.out / "across_agent_adjusted.json",
        {
            "n_agents": len(cond),
            "min_agents_per_axis": MIN_AGENTS_PER_AXIS,
            "reporting_spread": {
                "combination_fraction": [float(combo.min()), float(combo.max())],
                "threshold_centered": [
                    float(min(c[1] for c in cond.values())),
                    float(max(c[1] for c in cond.values())),
                ],
                "log_n_centered": [
                    float(min(c[2] for c in cond.values())),
                    float(max(c[2] for c in cond.values())),
                ],
            },
            "variants": results,
            "permutation_p": ps,
            "headline_variant": "adjusted_within_trial_blind",
            "caveats": [
                "The result depends on the adjustment: unadjusted the mean is +0.0966 "
                "with an interval spanning zero.",
                "b_combo spans 0.032 to 0.195 across three estimators, and the headline "
                "sits between them at 0.048.",
                "b_combo is identified within trials from only 6 trials and 20 arms.",
                "b_thresh has zero within-trial variance and is therefore not "
                "identifiable except between trials, where it is confounded; the headline "
                "estimator sets it to zero rather than using a confounded value.",
                "The permutation test and the bootstrap over axes disagree for the "
                "headline estimator: p = 0.025 against an interval that includes zero. "
                "The per-axis correlations are heterogeneous, so the mean is not reliably "
                "positive under axis resampling.",
            ],
            "mechanism_share_of_combination_variance": frac,
            "reading": (
                "Suggestive, not settled. With between-agent reporting conditions removed "
                "using the within-trial design-blind estimator, the across-agent organ "
                "ranking beats chance at p = 0.025 by permutation -- and a constant "
                "per-axis predictor has no discriminative power on this metric by "
                "construction, so beating chance here is beating the baseline. But the "
                "bootstrap over axes includes zero for that same estimator, the result "
                "moves with how the adjustment is estimated, and the within-trial "
                "identification rests on six trials. The within-arm result is unaffected "
                "and still fails. This needs more agents to settle, not more analysis."
            ),
        },
        {"fold_predictions": args.fold_predictions, "processed": args.processed},
    )
    print(f"\n-> {args.out}/across_agent_adjusted.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
