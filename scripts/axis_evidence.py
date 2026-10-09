"""How many agents does each organ axis actually rest on, and which axes stop growing?

The product returns fourteen organ rates for every design, and the interface greys out an
axis with "no evidence in the training set". That hatching has never been driven by a
measurement -- it was driven by whether a cell existed at all, which is a weaker question
than whether the *design terms* on that axis rest on anything, since design features are
agent-level constants and an axis estimated from six agents is estimated from six.

Measured across the corpus stages, thirteen of the fourteen axes gain agents as the corpus
grows and one does not move at all. Otologic stands at the same 104 observed cells over the
same 18 agents on the registry corpus, on the literature-extended corpus and on the corpus
merged with the hand-transcribed database -- 46 new agents contributed nothing to it. The
reason is the one negative result 34 measured on the other axes, in its total form: of the
agents with arms from both a registry and a paper, the papers report **zero** otologic
observations against the registry's 96. Papers about ADCs do not mention hearing.

So for one organ of fourteen the design coefficients are estimated from 28% of the agents
the other axes see, and that is a fact about the literature rather than about the ear.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.model import dataset as ds
from adctox.model.dataset import OBSERVED
from adctox.provenance import write_json
from adctox.taxonomy import Taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]

STAGES = [
    ("registry", "data/processed"),
    ("plus_literature", "data/processed/with_literature_final"),
    ("plus_transcribed", "data/processed/with_atlas"),
]

# Below this share of the corpus's agents, an axis's design terms rest on a minority of the
# evidence and the interface should say so rather than print a number like any other.
THIN_AGENT_SHARE = 0.5


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "axis_evidence.json")
    args = ap.parse_args()

    axes = list(Taxonomy().axis_order)
    stages: dict[str, dict] = {}
    for name, rel in STAGES:
        path = ROOT / rel
        if not (path / "arms.parquet").exists():
            continue
        data = ds.load(path, axes, kind="other")
        agent_of_cell = np.asarray(data.arm_agent_idx)[data.arm_idx]
        observed = data.status == OBSERVED
        per_axis = {}
        for ai, axis in enumerate(axes):
            sel = observed & (data.axis_idx == ai)
            agents = {int(a) for a in agent_of_cell[sel]}
            per_axis[axis] = {
                "observed_cells": int(sel.sum()),
                "agents": len(agents),
                "agent_share": round(len(agents) / max(len(data.agents), 1), 4),
            }
        stages[name] = {"corpus_agents": len(data.agents), "axes": per_axis}

    first, last = STAGES[0][0], STAGES[-1][0]
    growth = []
    if first in stages and last in stages:
        for axis in axes:
            a = stages[first]["axes"][axis]
            b = stages[last]["axes"][axis]
            growth.append({
                "axis": axis,
                "agents_first": a["agents"],
                "agents_last": b["agents"],
                "agents_gained": b["agents"] - a["agents"],
                "cells_gained": b["observed_cells"] - a["observed_cells"],
                "agent_share_last": b["agent_share"],
                # An axis that gains nothing from a doubled corpus is not waiting on more
                # work; something systematic is keeping it out.
                "stalled": b["agents"] == a["agents"],
                "thin": b["agent_share"] < THIN_AGENT_SHARE,
            })
        growth.sort(key=lambda r: r["agents_gained"])

    doc = {
        "thin_agent_share": THIN_AGENT_SHARE,
        "stages": stages,
        "growth": growth,
        "summary": {
            "n_axes": len(axes),
            "stalled_axes": [r["axis"] for r in growth if r["stalled"]],
            "thin_axes": [r["axis"] for r in growth if r["thin"]],
            "corpus_agents_first": stages.get(first, {}).get("corpus_agents"),
            "corpus_agents_last": stages.get(last, {}).get("corpus_agents"),
        },
    }
    write_json(args.out, doc)

    if growth:
        print(f"{'axis':22} {'agents first':>13} {'agents last':>12} {'gained':>7} "
              f"{'share':>7}  flag")
        for r in sorted(growth, key=lambda r: -r["agents_last"]):
            flag = "STALLED" if r["stalled"] else ("thin" if r["thin"] else "")
            print(f"{r['axis']:22} {r['agents_first']:>13} {r['agents_last']:>12} "
                  f"{r['agents_gained']:>7} {r['agent_share_last']:>7.2f}  {flag}")
        print()
        print(f"corpus went from {doc['summary']['corpus_agents_first']} agents to "
              f"{doc['summary']['corpus_agents_last']}")
        print(f"stalled: {doc['summary']['stalled_axes'] or 'none'}")
        print(f"thin (below {THIN_AGENT_SHARE:.0%} of agents): "
              f"{doc['summary']['thin_axes'] or 'none'}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
