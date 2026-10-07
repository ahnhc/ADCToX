#!/usr/bin/env python
"""Compare the model's organ ranking against the ordering in approved dose-modification tables.

The comparison this makes: a label's section-2 table says which organs to withhold or
discontinue for, and at what grade. That is the clinical community's operational ordering
of which organs it fears for that drug. Does the model's 14-axis ranking agree with it?

Two choices that decide whether the answer is meaningful:

* **Held-out predictions.** Per-agent predictions come from the leave-one-agent-out folds,
  so the model never saw the drug it is being scored on. Using the full fit would let it
  recall the arms that shaped the label.
* **Absence is informative, not missing.** A label giving no dose-modification instruction
  for an organ is saying none is needed, so unmentioned axes score zero rather than being
  dropped. The question is precisely whether the model ranks the feared organs above the
  rest.

Confound reported rather than removed: dose-modification tables are partly copied within a
payload class, so the three vedotins are not independent observations of the same
agreement. Per-mechanism results are given alongside the pooled figure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json  # noqa: E402

from adctox.taxonomy import Taxonomy  # noqa: E402
from adctox.validation.dose_modification import axis_concern, parse_tables  # noqa: E402

CONF = Path(__file__).resolve().parents[1] / "conf"


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or len(set(a.tolist())) < 2 or len(set(b.tolist())) < 2:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    den = np.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / den) if den else float("nan")


def _bootstrap_ci(vals: list[float], seed: int = 0, n: int = 4000) -> tuple[float, float]:
    arr = np.asarray([v for v in vals if np.isfinite(v)])
    if len(arr) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = [rng.choice(arr, len(arr), replace=True).mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--fold-predictions", type=Path,
                    default=Path("artifacts/forward_other_fold_predictions.parquet"))
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    tax = Taxonomy()
    axes = list(tax.axis_order)
    registry = yaml.safe_load((CONF / "adc_registry.yaml").read_text(encoding="utf-8"))["agents"]

    if not args.fold_predictions.exists():
        print(f"{args.fold_predictions} not found; run scripts/fit_forward.py first",
              file=sys.stderr)
        return 1
    folds = pd.read_parquet(args.fold_predictions)
    loao = folds[folds["split"] == "leave_one_agent_out"]
    if loao.empty:
        print("no leave-one-agent-out predictions in the fold table", file=sys.stderr)
        return 1

    rows = []
    for agent, grp in loao.groupby("fold"):
        label_path = args.labels / f"{agent}.json"
        if not label_path.exists():
            continue
        entries = parse_tables(
            agent,
            json.loads(label_path.read_text(encoding="utf-8")).get(
                "dosage_and_administration_table"
            )
            or [],
        )
        concern = axis_concern(entries)
        if len(concern) < 2:
            print(f"  {agent}: label names fewer than 2 organs; skipped")
            continue
        pred = grp.set_index("axis")["pred"]
        base_m = grp.set_index("axis")["pred_mech_baseline"]
        base_g = grp.set_index("axis")["pred_global_baseline"]
        # Absence is a zero, not a gap.
        y = np.array([concern.get(a, 0.0) for a in axes])
        x = np.array([float(pred.get(a, np.nan)) for a in axes])
        xm = np.array([float(base_m.get(a, np.nan)) for a in axes])
        xg = np.array([float(base_g.get(a, np.nan)) for a in axes])
        ok = ~np.isnan(x)
        if ok.sum() < 6:
            continue
        rows.append(
            {
                "agent": agent,
                "mechanism": registry[agent]["mechanism"],
                "n_axes_named": len(concern),
                "rho_model": _spearman(x[ok], y[ok]),
                "rho_mech_baseline": _spearman(xm[ok], y[ok]),
                "rho_global_baseline": _spearman(xg[ok], y[ok]),
                "top_label_axis": max(concern, key=concern.get),
                "top_model_axis": axes[int(np.nanargmax(np.where(ok, x, -np.inf)))],
            }
        )

    if not rows:
        print("no agent could be scored", file=sys.stderr)
        return 1

    df = pd.DataFrame(rows).sort_values("rho_model", ascending=False)
    print(f"{len(df)} agents scored, held-out predictions\n")
    print(f"  {'agent':26s} {'model':>7s} {'mech':>7s} {'global':>7s}  "
          f"{'label top':20s} {'model top':20s}")
    for r in df.itertuples():
        match = " *" if r.top_label_axis == r.top_model_axis else ""
        print(f"  {r.agent:26s} {r.rho_model:+7.3f} {r.rho_mech_baseline:+7.3f} "
              f"{r.rho_global_baseline:+7.3f}  {r.top_label_axis:20s} "
              f"{r.top_model_axis:20s}{match}")

    mm = df["rho_model"].mean()
    lo, hi = _bootstrap_ci(df["rho_model"].tolist())
    bm = df["rho_mech_baseline"].mean()
    bg = df["rho_global_baseline"].mean()
    # The model's own CI excluding zero only says the label ordering is not random. What
    # decides whether the *model* contributes is the paired difference against the
    # strongest baseline, bootstrapped over agents -- the same logic as the delta-AUC gate.
    best_name = "global" if bg >= bm else "mech"
    best_col = "rho_global_baseline" if bg >= bm else "rho_mech_baseline"
    diffs = (df["rho_model"] - df[best_col]).tolist()
    dlo, dhi = _bootstrap_ci(diffs, seed=7)
    top_hits = int((df["top_label_axis"] == df["top_model_axis"]).sum())
    print(f"\n  mean Spearman   model {mm:+.3f}  [{lo:+.3f}, {hi:+.3f}]"
          f"{'  excludes 0' if lo > 0 or hi < 0 else '  INCLUDES 0'}")
    print(f"                  mech baseline {bm:+.3f} | global baseline {bg:+.3f}")
    print(f"  paired delta vs the {best_name} baseline: {np.mean(diffs):+.3f} "
          f"[{dlo:+.3f}, {dhi:+.3f}]"
          f"{'  excludes 0' if dlo > 0 or dhi < 0 else '  INCLUDES 0'}")
    exp = len(df) / 14
    print(f"  top-organ agreement {top_hits}/{len(df)} "
          f"(expected {exp:.2f} by chance)"
          f"{'  -- at chance' if abs(top_hits - exp) < 1.5 else ''}")
    # A model whose top axis is the same organ for most drugs is reporting a base rate,
    # not a per-drug judgement, and saying so is more useful than the correlation alone.
    modal = df["top_model_axis"].value_counts()
    print(f"  the model names {modal.index[0]} as the top axis for "
          f"{modal.iloc[0]}/{len(df)} drugs, which is a base-rate effect rather than a "
          f"per-drug judgement")

    print(f"\n  by mechanism -- dose-modification tables are partly copied within a payload")
    print(f"  class, so same-mechanism agents are not independent observations")
    for mech, grp in df.groupby("mechanism"):
        print(f"    {mech:16s} n={len(grp)}  mean rho {grp['rho_model'].mean():+.3f}")

    out = {
        "n_agents": len(df),
        "mean_rho_model": float(mm), "rho_ci": [lo, hi],
        "mean_rho_mech_baseline": float(bm),
        "mean_rho_global_baseline": float(bg),
        "paired_delta_vs_best_baseline": float(np.mean(diffs)),
        "paired_delta_ci": [dlo, dhi],
        "best_baseline": best_name,
        "modal_model_top_axis": str(df["top_model_axis"].value_counts().index[0]),
        "modal_model_top_axis_count": int(df["top_model_axis"].value_counts().iloc[0]),
        "top_organ_agreement": f"{top_hits}/{len(df)}",
        "per_agent": df.to_dict("records"),
    }
    path = args.out / "dose_mod_eval.json"
    write_json(path, out, {"labels": args.labels})
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
