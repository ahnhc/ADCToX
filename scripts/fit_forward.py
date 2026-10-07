#!/usr/bin/env python
"""Fit the forward model, run the held-out folds, report the honest numbers.

Metric discipline, decided before seeing results:

* The headline is **delta against the mechanism-group-mean baseline**, with a bootstrap
  CI -- not an absolute AUC. An absolute AUC near 0.75 on a 14-axis ranking task is
  reachable by the global axis mean alone, because every cytotoxic hits GI and blood and
  that base rate dominates the ranking. Reporting it would be reporting the base rate.
* Baseline 1 (global axis mean) is reported precisely to show that.
* The gate is macro AUC < 0.65 on held-out agents; below that the project's cut order
  fires. Stated in advance so it cannot be renegotiated afterwards.
* `tau_mech`, the learned scale on the mechanism x axis interaction, is reported as a
  first-class result. If the posterior collapses toward zero the data did not support
  the interaction, and that is the finding.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import jax
import numpy as np
import numpyro
from numpyro.infer import MCMC, NUTS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.model import dataset as ds, forward, splits  # noqa: E402
from adctox.model.dataset import CENSORED, ModelData  # noqa: E402
from adctox.taxonomy import Taxonomy  # noqa: E402

numpyro.set_host_device_count(2)


def _masked(data: ModelData, mask: np.ndarray) -> ModelData:
    """Subset a ModelData to a cell mask, keeping all arm-level arrays intact."""
    import dataclasses

    return dataclasses.replace(
        data,
        status=data.status[mask],
        n_affected=data.n_affected[mask],
        n_at_risk=data.n_at_risk[mask],
        censor_below=data.censor_below[mask],
        axis_idx=data.axis_idx[mask],
        arm_idx=data.arm_idx[mask],
    )


def fit(data: ModelData, hold_mech: int | None, seed: int, warmup: int, samples: int):
    # max_tree_depth is capped at 8 rather than left at the default 10. Measured on this
    # model: the default averages 479 gradient evaluations per iteration against 255 at
    # depth 8, for a 2.5x speedup, while the sampler stays healthy (0 divergences,
    # acceptance 0.84 against a 0.8 target). The geometry is not the problem here --
    # there is no funnel to fight, the trajectories are simply long.
    kernel = NUTS(forward.model, target_accept_prob=0.8, max_tree_depth=8)
    mcmc = MCMC(
        kernel, num_warmup=warmup, num_samples=samples, num_chains=2,
        progress_bar=False, chain_method="sequential",
    )
    mcmc.run(jax.random.PRNGKey(seed), data=data, hold_mech=hold_mech)
    return mcmc.get_samples()


def predict_rates(post: dict, data: ModelData, hold_mech: int | None) -> np.ndarray:
    """Posterior-mean rate per (arm, axis) cell, computed from the parameter draws."""
    mu = np.asarray(post["mu_axis"])                       # (S, A)
    mech = np.asarray(post["tau_mech"])[:, None, None] * np.asarray(post["mech_axis_raw"])
    if hold_mech is not None:
        mech = mech.copy()
        mech[:, hold_mech, :] = 0.0
    cleav = np.asarray(post["tau_cleav"])[:, None] * np.asarray(post["cleav_axis_raw"])
    arm_lin = (
        np.asarray(post["b_dar"])[:, None] * data.arm_dar_c[None, :]
        + np.asarray(post["b_combo"])[:, None] * data.arm_combo[None, :]
        + np.asarray(post["b_thresh"])[:, None] * data.arm_thresh_c[None, :]
        + np.asarray(post["b_log_n"])[:, None] * data.arm_log_n_c[None, :]
        + np.asarray(post["sigma_trial"])[:, None]
        * np.asarray(post["u_trial"])[:, data.arm_trial_idx]
        + np.asarray(post["sigma_agent"])[:, None]
        * np.asarray(post["u_agent"])[:, data.arm_agent_idx]
    )
    ai, xi = data.arm_idx, data.axis_idx
    logit = (
        mu[:, xi]
        + mech[:, data.arm_mech_idx[ai], xi]
        + cleav[:, xi] * data.arm_cleavable[ai][None, :]
        + arm_lin[:, ai]
    )
    return 1.0 / (1.0 + np.exp(-logit.mean(axis=0)))


def _observed_rate(data: ModelData, mask: np.ndarray) -> np.ndarray:
    """Observed rate per cell; censored cells get the threshold midpoint as a stand-in.

    Only used for *scoring*, never for fitting -- the fit treats them as censored.
    """
    rate = data.n_affected[mask] / np.maximum(data.n_at_risk[mask], 1)
    cens = data.status[mask] == CENSORED
    if cens.any():
        half = 0.5 * data.censor_below[mask] / np.maximum(data.n_at_risk[mask], 1)
        rate = np.where(cens, half, rate)
    return rate


def _auc_top3(pred: np.ndarray, obs: np.ndarray, axis_idx: np.ndarray, arm_idx: np.ndarray) -> float:
    """AUROC for "this axis is among the arm's observed top-3 axes"."""
    pos, neg = [], []
    for arm in np.unique(arm_idx):
        sel = arm_idx == arm
        if sel.sum() < 4:
            continue
        o, p = obs[sel], pred[sel]
        top3 = set(np.argsort(-o)[:3].tolist())
        for i, score in enumerate(p):
            (pos if i in top3 else neg).append(score)
    if not pos or not neg:
        return float("nan")
    pos_a, neg_a = np.asarray(pos), np.asarray(neg)
    wins = (pos_a[:, None] > neg_a[None, :]).sum() + 0.5 * (
        pos_a[:, None] == neg_a[None, :]
    ).sum()
    return float(wins / (len(pos_a) * len(neg_a)))


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    den = np.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / den) if den else float("nan")


def _bootstrap_ci(values: list[float], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    arr = np.asarray([v for v in values if np.isfinite(v)])
    if len(arr) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_boot)]
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=Path, default=Path("data/processed"))
    ap.add_argument("--kind", default="other", choices=["other", "serious"])
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    ap.add_argument("--warmup", type=int, default=500)
    ap.add_argument("--samples", type=int, default=500)
    # Cross-validation needs only posterior-mean predictions, so the 18 refits run at a
    # lower sample count than the fit whose posterior actually gets reported. Keeping the
    # two separate is what makes leave-one-agent-out affordable on CPU.
    ap.add_argument("--cv-warmup", type=int, default=200)
    ap.add_argument("--cv-samples", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--gate-auc", type=float, default=0.65)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    tax = Taxonomy()
    data = ds.load(args.processed, list(tax.axis_order), kind=args.kind)
    print(f"Corpus ({args.kind}): {data.summary()}", flush=True)
    acct = forward.n_free_parameters(data)
    print(
        f"\nParameters: design {acct['design']}, nuisance {acct['nuisance']}; "
        f"identifying cells {acct['identifying_cells']} "
        f"(ratio {acct['design_ratio_vs_identifying']}:1)"
    )
    print("\nFolds:"); print(splits.fold_report(data))

    # ---------------------------------------------------------------- full fit
    t0 = time.time()
    post = fit(data, None, args.seed, args.warmup, args.samples)
    print(f"\nFull fit: {time.time() - t0:.1f}s", flush=True)
    tau = np.asarray(post["tau_mech"])
    tau_c = np.asarray(post["tau_cleav"])
    print(
        f"  tau_mech  (mechanism x axis scale): "
        f"{tau.mean():.3f} [{np.percentile(tau, 5):.3f}, {np.percentile(tau, 95):.3f}]"
    )
    print(
        f"  tau_cleav (cleavability x axis)   : "
        f"{tau_c.mean():.3f} [{np.percentile(tau_c, 5):.3f}, {np.percentile(tau_c, 95):.3f}]"
    )
    for name in ("b_dar", "b_combo", "b_thresh", "b_log_n", "sigma_trial", "sigma_agent"):
        v = np.asarray(post[name])
        print(f"  {name:12s} {v.mean():+.3f} [{np.percentile(v, 5):+.3f}, {np.percentile(v, 95):+.3f}]")

    # ------------------------------------------------------------- baselines
    all_rate = _observed_rate(data, np.ones(data.n_cells, bool))
    global_axis_mean = np.zeros(len(data.axes))
    for a in range(len(data.axes)):
        global_axis_mean[a] = all_rate[data.axis_idx == a].mean()

    def mech_axis_mean(train: np.ndarray) -> np.ndarray:
        """Per-(mechanism, axis) mean rate on the training cells; the real baseline."""
        out = np.tile(global_axis_mean, (len(data.mechanisms), 1))
        tr_rate = _observed_rate(data, train)
        tr_axis = data.axis_idx[train]
        tr_mech = data.arm_mech_idx[data.arm_idx[train]]
        for m in range(len(data.mechanisms)):
            for a in range(len(data.axes)):
                sel = (tr_mech == m) & (tr_axis == a)
                if sel.sum() >= 3:
                    out[m, a] = tr_rate[sel].mean()
        return out

    results: dict[str, dict] = {}
    for fold_set, label in (
        (splits.leave_one_mechanism_out(data), "leave_one_mechanism_out"),
        (splits.leave_one_agent_out(data), "leave_one_agent_out"),
    ):
        print(f"\n{'=' * 74}\n{label}  ({len(fold_set)} folds)\n{'=' * 74}")
        rows = []
        for fold in fold_set:
            train_data = _masked(data, fold.train_cells)
            t_fold = time.time()
            p_fold = fit(train_data, fold.held_mech_idx, args.seed + 1,
                         args.cv_warmup, args.cv_samples)
            test = _masked(data, fold.test_cells)
            pred = predict_rates(p_fold, test, fold.held_mech_idx)
            obs = _observed_rate(data, fold.test_cells)

            base_mech = mech_axis_mean(fold.train_cells)
            t_mech = data.arm_mech_idx[test.arm_idx]
            pred_mech_base = base_mech[t_mech, test.axis_idx]
            pred_global_base = global_axis_mean[test.axis_idx]

            auc_m = _auc_top3(pred, obs, test.axis_idx, test.arm_idx)
            auc_b = _auc_top3(pred_mech_base, obs, test.axis_idx, test.arm_idx)
            auc_g = _auc_top3(pred_global_base, obs, test.axis_idx, test.arm_idx)
            sp_m = _spearman(pred, obs)
            sp_b = _spearman(pred_mech_base, obs)
            mae = float(np.abs(pred - obs).mean())
            mae_b = float(np.abs(pred_mech_base - obs).mean())

            rows.append(
                {
                    "fold": fold.name, "n_test_cells": int(fold.test_cells.sum()),
                    "auc_model": auc_m, "auc_mech_baseline": auc_b, "auc_global_baseline": auc_g,
                    "delta_auc": auc_m - auc_b,
                    "spearman_model": sp_m, "spearman_mech_baseline": sp_b,
                    "mae_model": mae, "mae_mech_baseline": mae_b,
                }
            )
            print(
                f"  {fold.name:26s} AUC {auc_m:.3f} vs mech {auc_b:.3f} "
                f"(d {auc_m - auc_b:+.3f}) | global {auc_g:.3f} | "
                f"MAE {mae:.3f} vs {mae_b:.3f} | {time.time() - t_fold:.0f}s",
                flush=True,
            )

        d_auc = [r["delta_auc"] for r in rows]
        lo, hi = _bootstrap_ci(d_auc, seed=args.seed)
        macro = float(np.nanmean([r["auc_model"] for r in rows]))
        macro_b = float(np.nanmean([r["auc_mech_baseline"] for r in rows]))
        macro_g = float(np.nanmean([r["auc_global_baseline"] for r in rows]))
        print(f"\n  macro AUC   model {macro:.3f} | mech-mean {macro_b:.3f} | global-mean {macro_g:.3f}")
        print(f"  delta AUC   {np.nanmean(d_auc):+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]"
              f"{'  (excludes 0)' if lo > 0 or hi < 0 else '  (INCLUDES 0)'}")
        results[label] = {
            "folds": rows, "macro_auc": macro, "macro_auc_mech_baseline": macro_b,
            "macro_auc_global_baseline": macro_g,
            "delta_auc_mean": float(np.nanmean(d_auc)), "delta_auc_ci": [lo, hi],
        }

    gate_key = "leave_one_agent_out"
    gate_auc = results[gate_key]["macro_auc"]
    passed = gate_auc >= args.gate_auc
    out = {
        "kind": args.kind, "corpus": data.summary(), "parameters": acct,
        "tau_mech": {"mean": float(tau.mean()),
                     "q05": float(np.percentile(tau, 5)), "q95": float(np.percentile(tau, 95))},
        "tau_cleav": {"mean": float(tau_c.mean())},
        "coefficients": {
            k: {"mean": float(np.asarray(post[k]).mean()),
                "q05": float(np.percentile(np.asarray(post[k]), 5)),
                "q95": float(np.percentile(np.asarray(post[k]), 95))}
            for k in ("b_dar", "b_combo", "b_thresh", "b_log_n", "sigma_trial", "sigma_agent")
        },
        "cv": results,
        "gate": {"metric": f"macro_auc[{gate_key}]", "value": gate_auc,
                 "threshold": args.gate_auc, "pass": passed},
    }
    path = args.out / f"forward_{args.kind}_metrics.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n-> {path}")
    print(f"\nGATE (macro AUC, {gate_key}): {gate_auc:.3f} vs {args.gate_auc} -> "
          f"{'PASS' if passed else 'FAIL -> cut order fires'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
