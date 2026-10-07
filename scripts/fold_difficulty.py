#!/usr/bin/env python
"""What makes a leave-one-agent-out fold hard?

The model card asserted it: "every large miss is an agent that is the sole representative
of its payload family inside a broader mechanism class". It also said, honestly, that the
numbers were from the pre-fix model and that whether the pattern survived the re-run was
itself a result. It did not survive, and this script is how that was established.

On the split-corrected folds, none of the four worst is the sole representative of its
family, and the two worst -- trastuzumab emtansine and mirvetuximab soravtansine -- are
each other's only family sibling. Mean delta for sole-of-family agents is -0.0485 against
-0.0408 for agents that share one, on 3 against 13 agents: no separation.

What does track fold difficulty is coarser and worse for the project. Measured here as
rank correlations against the fold's delta (higher delta = better predicted):

  * how many agents share the held-out agent's PAYLOAD
  * what share of its mechanism's agents belong to its payload family

The first is the stronger of the two. That matters because payload is the level this
corpus provably cannot reach -- the payload vocabulary grows as fast as the corpus, 9 to
20 classes from 17 to 54 agents -- whereas family at least stops growing. So the honest
version of the squeeze is tighter than the version the model card claimed.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json  # noqa: E402

CONF = Path(__file__).resolve().parents[1] / "conf"


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    rx -= rx.mean()
    ry -= ry.mean()
    den = np.sqrt((rx**2).sum() * (ry**2).sum())
    return float((rx * ry).sum() / den) if den else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", type=Path,
                    default=Path("artifacts/forward_other_metrics.json"))
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    args = ap.parse_args()

    import json

    if not args.metrics.exists():
        print(f"{args.metrics} absent; run `make forward`")
        return 1
    folds = json.loads(args.metrics.read_text(encoding="utf-8"))[
        "cv"]["leave_one_agent_out"]["folds"]
    reg = yaml.safe_load((CONF / "adc_registry.yaml").read_text(encoding="utf-8"))["agents"]

    delta = {f["fold"]: f["delta_auc"] for f in folds}
    agents = [a for a in delta if a in reg]
    fam = {a: reg[a]["payload_family"] for a in agents}
    mech = {a: reg[a]["mechanism"] for a in agents}
    pay = {a: reg[a]["payload"] for a in agents}
    # Counted over the FITTED corpus, not the registry: the registry holds an agent the
    # design matrix cannot represent, and counting it would inflate every denominator.
    n_mech, n_fam, n_pay = Counter(mech.values()), Counter(fam.values()), Counter(pay.values())

    rows = []
    for a in sorted(agents, key=lambda x: delta[x]):
        rows.append({
            "agent": a, "delta_auc": delta[a],
            "payload": pay[a], "payload_family": fam[a], "mechanism": mech[a],
            "same_payload_siblings": n_pay[pay[a]] - 1,
            "family_share_of_mechanism": n_fam[fam[a]] / n_mech[mech[a]],
            "sole_of_family": n_fam[fam[a]] == 1,
        })

    d = np.array([r["delta_auc"] for r in rows])
    sib = np.array([r["same_payload_siblings"] for r in rows], dtype=float)
    share = np.array([r["family_share_of_mechanism"] for r in rows])
    rho_sib, rho_share = _spearman(d, sib), _spearman(d, share)

    sole = [r["delta_auc"] for r in rows if r["sole_of_family"]]
    shared = [r["delta_auc"] for r in rows if not r["sole_of_family"]]
    worst4 = rows[:4]

    print("Fold difficulty, leave-one-agent-out, split-corrected folds\n")
    print(f"  {'agent':28s} {'delta':>8s} {'siblings':>9s} {'fam share':>10s}  sole?")
    for r in rows:
        print(f"  {r['agent']:28s} {r['delta_auc']:+8.4f} "
              f"{r['same_payload_siblings']:9d} {r['family_share_of_mechanism']:10.2f}"
              f"  {'YES' if r['sole_of_family'] else ''}")
    print(f"\n  the claim the model card made: every large miss is sole-of-family")
    print(f"    sole-of-family among the 4 worst folds : "
          f"{sum(1 for r in worst4 if r['sole_of_family'])}/4")
    print(f"    mean delta, sole-of-family  ({len(sole):2d})     : {np.mean(sole):+.4f}")
    print(f"    mean delta, shares a family ({len(shared):2d})     : {np.mean(shared):+.4f}")
    print(f"    -> not supported")
    print(f"\n  what does track difficulty (rank correlation with delta)")
    print(f"    same-payload siblings        : {rho_sib:+.3f}")
    print(f"    family share of its mechanism: {rho_share:+.3f}")

    write_json(
        args.out / "fold_difficulty.json",
        {
            "folds": rows,
            "sole_of_family_claim": {
                "sole_among_worst_four": sum(1 for r in worst4 if r["sole_of_family"]),
                "mean_delta_sole": float(np.mean(sole)) if sole else None,
                "mean_delta_shared": float(np.mean(shared)) if shared else None,
                "n_sole": len(sole), "n_shared": len(shared),
                "supported": False,
            },
            "spearman_delta_vs": {
                "same_payload_siblings": rho_sib,
                "family_share_of_mechanism": rho_share,
            },
        },
        {"metrics": args.metrics, "registry": CONF / "adc_registry.yaml"},
    )
    print(f"\n-> {args.out}/fold_difficulty.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
