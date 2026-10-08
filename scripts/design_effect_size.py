#!/usr/bin/env python
"""How large are the fitted design effects, relative to the baseline they have to move?

This is the mechanism behind the project's headline negative result. The model loses to a
predictor that knows only the per-axis base rates, and until now that was an empirical
fact without an explanation. The explanation is a ratio.

Within one arm the organ ranking is set by `mu_axis + design effects`. If the design
effects are small against the spread of `mu_axis`, the ranking is the baseline's ranking
and the design terms can only add noise. Measured:

    mechanism       agents   effect sd / mu sd   rank corr with baseline
    tubulin              7                0.29                     0.947
    topo1                4                0.36                     0.969
    dna_alkyl            1                0.71                     0.670

So the mechanisms with the most evidence reshuffle the organ order least, and the
mechanism carried by a single drug reshuffles it most. Both halves are bad in different
directions: where the data is good the signal is too weak to beat a base rate, and where
the signal is strong the data is one drug.

The second half has a cause worth naming. A design coefficient is identified by agents,
not patients -- that is this project's central structural finding -- but the binomial
likelihood counts patients. A cell with two arms still carries several hundred patients,
so the likelihood is confident about it, and the hierarchical prior is not strong enough
to say that two arms of one drug cannot settle a chemistry effect. Hence `dna_alkyl`'s
ocular coefficient at +1.98 on 2 arms beside `tubulin`'s neurologic at +1.06 on 163.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.model.predict import Posterior  # noqa: E402
from adctox.provenance import write_json  # noqa: E402


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    rx -= rx.mean()
    ry -= ry.mean()
    den = np.sqrt((rx**2).sum() * (ry**2).sum())
    return float((rx * ry).sum() / den) if den else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--posterior", type=Path, default=Path("artifacts/posterior_other.npz"))
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    args = ap.parse_args()

    if not args.posterior.exists():
        print(f"{args.posterior} absent; run `make forward`")
        return 1
    post = Posterior.load(args.posterior)
    mu = post.mu_axis.mean(axis=0)
    mech = post.mech_axis.mean(axis=0)
    cleav = post.cleav_axis.mean(axis=0)
    arms = np.asarray(post.evidence_arms)
    agents = np.asarray(post.evidence_agents)
    mu_sd = float(mu.std())

    print(f"baseline spread across axes: sd {mu_sd:.3f}, "
          f"range {mu.min():.2f} to {mu.max():.2f}\n")
    print(f"  {'mechanism':16s} {'agents':>6s} {'eff sd':>7s} {'ratio':>6s} "
          f"{'rank corr':>9s} {'positions moved':>15s}")
    rows = []
    base_order = np.argsort(np.argsort(-mu))
    for i, name in enumerate(post.mechanisms):
        effect = mech[i]
        moved = int(np.abs(base_order - np.argsort(np.argsort(-(mu + effect)))).sum())
        rho = _spearman(mu, mu + effect)
        n_agents = int(agents[i].max())
        rows.append({
            "mechanism": name, "n_agents": n_agents,
            "effect_sd": float(effect.std()),
            "ratio_to_baseline_sd": float(effect.std() / mu_sd),
            "rank_corr_with_baseline": rho,
            "axis_positions_moved": moved,
        })
        print(f"  {name:16s} {n_agents:6d} {effect.std():7.3f} "
              f"{effect.std()/mu_sd:6.2f} {rho:9.3f} {moved:15d}")

    cl = {
        "effect_sd": float(cleav.std()),
        "ratio_to_baseline_sd": float(cleav.std() / mu_sd),
        "rank_corr_with_baseline": _spearman(mu, mu + cleav),
    }
    print(f"\n  cleavability: sd {cl['effect_sd']:.3f}, ratio "
          f"{cl['ratio_to_baseline_sd']:.2f}, rank corr "
          f"{cl['rank_corr_with_baseline']:.3f}")

    # Is the signal where the evidence is?
    cells = [
        {"mechanism": post.mechanisms[i], "axis": post.axes[j],
         "effect": float(mech[i][j]), "abs_effect": abs(float(mech[i][j])),
         "arms": int(arms[i][j]), "agents": int(agents[i][j])}
        for i in range(len(post.mechanisms)) for j in range(len(post.axes))
    ]
    cells.sort(key=lambda c: -c["abs_effect"])
    rho_arms = _spearman(
        np.array([c["abs_effect"] for c in cells]),
        np.array([float(c["arms"]) for c in cells]),
    )
    print(f"\n  largest design effects, and the evidence under them:")
    print(f"    {'|effect|':>8s} {'mechanism':16s} {'axis':20s} {'arms':>5s} {'agents':>6s}")
    for c in cells[:6]:
        print(f"    {c['abs_effect']:8.2f} {c['mechanism']:16s} {c['axis']:20s} "
              f"{c['arms']:5d} {c['agents']:6d}")
    print(f"\n  rank correlation of |effect| with supporting arms: {rho_arms:+.3f}")
    print("    negative means the biggest fitted effects sit on the thinnest evidence")

    write_json(
        args.out / "design_effect_size.json",
        {
            "baseline_sd": mu_sd,
            "baseline_range": [float(mu.min()), float(mu.max())],
            "per_mechanism": rows,
            "cleavability": cl,
            "effect_vs_evidence_spearman": rho_arms,
            "largest_cells": cells[:12],
            "reading": (
                "Where the evidence is good the design effects are too small to reorder "
                "the organ ranking (tubulin ratio 0.29, rank corr 0.947), so the "
                "within-arm metric is the baseline's metric and the design terms only add "
                "noise. Where the effects are large the evidence is one drug (dna_alkyl "
                "ratio 0.71 on a single agent). A design coefficient is identified by "
                "agents, not patients, but the binomial likelihood counts patients, so a "
                "two-arm cell still carries hundreds of patients and the hierarchical "
                "prior does not shrink it enough."
            ),
        },
        {"posterior": args.posterior},
    )
    print(f"\n-> {args.out}/design_effect_size.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
