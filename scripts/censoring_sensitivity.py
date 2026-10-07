#!/usr/bin/env python
"""Show what the naive alternative to the censored likelihood does.

The censored treatment is the single most consequential modelling choice in the project,
and "we handled censoring correctly" is not a claim a reader can check. This script makes
it checkable by fitting the same model three ways and comparing the threshold coefficient:

1. **censored** -- a cell missing from a truncated otherEvents table contributes
   log P(X < cut), the correct likelihood.
2. **zero-imputed** -- the same cell is treated as an observed zero. This is the naive
   choice, and because the reporting cut is sponsor-chosen while agents nest inside
   sponsors, the induced bias aliases the payload-mechanism effect rather than being
   absorbed by the trial random effect.
3. **threshold-0 only** -- restricted to the 182 studies that report completely, so no
   censoring model is needed at all. The smallest and cleanest corpus.

What would falsify the censored treatment: if `b_thresh` were near zero under
zero-imputation too, the correction would be solving a problem that does not exist. If the
mechanism x axis profile under (1) disagreed with (3), the correction would be *creating*
the signal rather than recovering it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jax
import numpy as np
import pandas as pd
from numpyro.infer import MCMC, NUTS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.model import dataset as ds, forward  # noqa: E402
from adctox.model.dataset import CENSORED, OBSERVED, ZERO  # noqa: E402
from adctox.taxonomy import Taxonomy  # noqa: E402


def _fit(data, warmup: int, samples: int, seed: int) -> dict:
    mcmc = MCMC(
        NUTS(forward.model, target_accept_prob=0.8, max_tree_depth=8),
        num_warmup=warmup, num_samples=samples, num_chains=1, progress_bar=False,
    )
    mcmc.run(jax.random.PRNGKey(seed), data=data)
    return mcmc.get_samples()


def _summarize(post: dict, data) -> dict:
    out = {}
    for name in ("tau_mech", "tau_cleav", "b_thresh", "b_dar", "b_combo", "b_log_n",
                 "sigma_trial", "sigma_agent"):
        v = np.asarray(post[name])
        out[name] = {
            "mean": float(v.mean()),
            "q05": float(np.percentile(v, 5)),
            "q95": float(np.percentile(v, 95)),
            "excludes_zero": bool(
                np.percentile(v, 5) > 0 or np.percentile(v, 95) < 0
            ),
        }
    # Mechanism x axis profile, so the three variants can be compared on substance and
    # not only on the nuisance coefficient.
    mech = np.asarray(post["tau_mech"])[:, None, None] * np.asarray(post["mech_axis_raw"])
    out["mech_axis_mean"] = {
        m: {a: float(mech[:, i, j].mean()) for j, a in enumerate(data.axes)}
        for i, m in enumerate(data.mechanisms)
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=Path, default=Path("data/processed"))
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--samples", type=int, default=300)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    tax = Taxonomy()
    axes = list(tax.axis_order)
    base = ds.load(args.processed, axes, kind="other")
    print(f"censored    : {base.summary()}")

    # Variant 2: the same cells, censoring discarded.
    import dataclasses

    naive = dataclasses.replace(
        base,
        status=np.where(base.status == CENSORED, ZERO, base.status),
        n_affected=np.where(base.status == CENSORED, 0, base.n_affected),
    )
    print(f"zero-imputed: {(naive.status == ZERO).sum():,} cells now treated as true zeros")

    # Variant 3: only the completely-reported studies.
    arms = pd.read_parquet(args.processed / "arms.parquet")
    obs = pd.read_parquet(args.processed / "observations.parquet")
    complete_ncts = set(arms.loc[arms["frequency_threshold"] == 0.0, "nct_id"])
    arms_c = arms[arms["nct_id"].isin(complete_ncts)]
    obs_c = obs[obs["nct_id"].isin(complete_ncts)]
    try:
        complete = ds.build(arms_c, obs_c, axes, kind="other")
        print(f"threshold-0 : {complete.summary()}")
    except ValueError as exc:
        print(f"threshold-0 : unavailable ({exc})")
        complete = None

    results = {}
    for label, data in (
        ("censored", base), ("zero_imputed", naive),
        *( (("threshold_0_only", complete),) if complete is not None else () ),
    ):
        print(f"\nfitting {label} ...", flush=True)
        post = _fit(data, args.warmup, args.samples, seed=11)
        results[label] = _summarize(post, data)
        bt = results[label]["b_thresh"]
        print(
            f"  b_thresh {bt['mean']:+.4f} [{bt['q05']:+.4f}, {bt['q95']:+.4f}]"
            f"  {'EXCLUDES 0' if bt['excludes_zero'] else 'includes 0'}"
        )

    print(f"\n{'=' * 70}\nthreshold coefficient by treatment\n{'=' * 70}")
    for label, res in results.items():
        bt = res["b_thresh"]
        print(f"  {label:18s} {bt['mean']:+.4f} [{bt['q05']:+.4f}, {bt['q95']:+.4f}]")
    print(
        "\nReading: a threshold coefficient that stays near zero under the censored\n"
        "likelihood but moves away from zero under zero-imputation is the expected\n"
        "signature -- it means the correction is absorbing a reporting artefact that would\n"
        "otherwise be attributed to the design."
    )

    # Substance check: do the censored and complete-reporting corpora agree on the
    # mechanism profiles? If not, the censoring model is creating signal, not recovering it.
    if complete is not None:
        shared = set(results["censored"]["mech_axis_mean"]) & set(
            results["threshold_0_only"]["mech_axis_mean"]
        )
        print(f"\nmechanism-profile agreement, censored vs threshold-0 ({len(shared)} shared)")
        for m in sorted(shared):
            a = np.array(list(results["censored"]["mech_axis_mean"][m].values()))
            b = np.array(list(results["threshold_0_only"]["mech_axis_mean"][m].values()))
            ra = np.argsort(np.argsort(a)).astype(float)
            rb = np.argsort(np.argsort(b)).astype(float)
            ra -= ra.mean(); rb -= rb.mean()
            rho = float((ra * rb).sum() / np.sqrt((ra**2).sum() * (rb**2).sum()))
            print(f"  {m:16s} Spearman {rho:+.3f}")

    path = args.out / "censoring_sensitivity.json"
    path.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
