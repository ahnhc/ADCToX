"""Is the literature-versus-registry gap one number or fourteen?

`b_source` was added as a single intercept shift because `b_combo` was absorbing it. A
single shift is the right first move and the wrong final one: a paper's adverse-event table
is selected for what is notable about *that* drug, so the organs it foregrounds and the
organs it drops below the reporting cut are not the same organs for every axis.

Measured on the 12 agents that have arms from both sources -- which holds the chemistry
fixed, so the gap is reporting rather than drug -- the gap runs from **-1.16 logit on
cardiovascular to +1.79 on ocular**, with between-axis heterogeneity at Q = 80 on 11 degrees
of freedom, p = 1.5e-12. The true between-axis standard deviation is about 0.72, which is
larger than `tau_mech`, the mechanism-by-axis scale the whole model exists to estimate.

The direction is interpretable and that is what makes it a specification error rather than
noise. Papers report *more* than the registry on ocular and dermatologic -- belantamab's
keratopathy and enfortumab's skin toxicity are the signature findings those papers are
about -- and *less* on cardiovascular, pulmonary, gastrointestinal and metabolic, which are
background and fall below a "most common adverse events" cut.

With one shift the axis-varying remainder has to go somewhere, and where it goes is
`mech_axis`, because literature arms are not spread evenly across mechanisms. So this is not
a nuisance refinement; it is a confound on the model's central parameter.
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np
import pandas as pd
from scipy import stats

from adctox.model.dataset import OBSERVED, build
from adctox.provenance import write_json
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIN_PER_SIDE = 6


def _logit(p: np.ndarray) -> np.ndarray:
    q = np.clip(p, 0.005, 0.995)
    return np.log(q / (1 - q))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_literature_final")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "source_axis_heterogeneity.json")
    args = ap.parse_args()

    axes = list(default_taxonomy().axis_order)
    arms = pd.read_parquet(args.processed / "arms.parquet")
    obs = pd.read_parquet(args.processed / "observations.parquet")
    data = build(arms, obs, axes, kind="other")

    mask = data.status == OBSERVED
    rate = data.n_affected[mask] / np.maximum(data.n_at_risk[mask], 1)
    arm = data.arm_idx[mask]
    lit = data.arm_is_literature[arm]
    agent = np.array([data.agents[i] for i in data.arm_agent_idx[arm]])
    axis = np.array([data.axes[i] for i in data.axis_idx[mask]])

    # Agents with arms from both sources. Without this the gap is partly the 15 agents the
    # literature brings, which is a drug difference and not a reporting one.
    both = sorted(
        a for a in set(agent)
        if (lit[agent == a] == 1).any() and (lit[agent == a] == 0).any()
    )
    keep = np.isin(agent, both)

    rows = []
    # An axis that cannot enter the comparison is not a gap in the measurement, it is the
    # measurement in miniature: otologic is excluded because the literature side is empty,
    # which is the same reporting selection the included axes quantify. So the exclusions
    # are recorded with their counts rather than silently dropped.
    excluded = []
    for a in axes:
        sel = keep & (axis == a)
        left = _logit(rate[sel & (lit == 1)])
        right = _logit(rate[sel & (lit == 0)])
        if len(left) < MIN_PER_SIDE or len(right) < MIN_PER_SIDE:
            excluded.append({
                "axis": a,
                "n_literature": int(len(left)),
                "n_registry": int(len(right)),
                "short_side": "literature" if len(left) < MIN_PER_SIDE else "registry",
            })
            continue
        se = float(np.sqrt(
            left.var(ddof=1) / len(left) + right.var(ddof=1) / len(right)
        ))
        rows.append({
            "axis": a, "n_literature": int(len(left)), "n_registry": int(len(right)),
            "gap_logit": float(left.mean() - right.mean()), "se": se,
        })

    g = np.array([r["gap_logit"] for r in rows])
    se = np.array([r["se"] for r in rows])
    weighted = float(np.average(g, weights=1 / se**2))
    q = float(np.sum((g - weighted) ** 2 / se**2))
    df = len(rows) - 1
    excess = float(g.var(ddof=1) - (se**2).mean())
    summary = {
        "agents_with_both_sources": len(both),
        "min_per_side": MIN_PER_SIDE,
        "axes_excluded": excluded,
        "axes_compared": len(rows),
        "weighted_mean_gap": round(weighted, 3),
        "gap_sd": round(float(g.std(ddof=1)), 3),
        "between_axis_sd": round(float(np.sqrt(max(excess, 0.0))), 3),
        "heterogeneity_q": round(q, 1),
        "df": df,
        "p": float(stats.chi2.sf(q, df)),
        "min_axis": rows[int(np.argmin(g))]["axis"],
        "max_axis": rows[int(np.argmax(g))]["axis"],
    }

    print(f"  {'axis':20s} {'lit':>5s} {'reg':>5s} {'gap':>7s} {'se':>6s}")
    for r in sorted(rows, key=lambda r: r["gap_logit"]):
        print(f"  {r['axis']:20s} {r['n_literature']:5d} {r['n_registry']:5d} "
              f"{r['gap_logit']:+7.2f} {r['se']:6.2f}")
    print()
    for k, v in summary.items():
        print(f"  {k:26s} {v}")
    write_json(args.out, {"summary": summary, "axes": rows})
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
