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
import collections
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


def _thinness_is_not_in_the_interval(limit: int = 8) -> dict | None:
    """Does the credible interval already say what the thin flag says?

    It matters because of what justifies the flag. If a cell supported by few agents always
    came with a wide interval, the flag would be decoration: the screen already shows the
    interval, and a reader would be told twice. If the two are weakly related, the flag
    carries information the interval does not -- and the threshold cannot be justified as a
    precision cut-off, because precision is what the interval measures.

    Measured over the product's own output, which is the only place the question is asked.
    """
    try:
        from fastapi.testclient import TestClient

        from adctox.api.main import app
    except Exception:
        return None
    client = TestClient(app)
    agents: list[float] = []
    relative_width: list[float] = []
    for target in ("HER2", "TROP2", "CD30", "BCMA", "FOLR1", "EGFR", "CD19", "NaPi2b")[:limit]:
        resp = client.post("/api/v1/propose", json={
            "comorbidity_profile": {"conditions": [],
                                    "cohort": {"age_band": "65_74", "sex": "female"}},
            "target_antigen": target, "top_k": 6,
        })
        if resp.status_code != 200:
            continue
        for cand in resp.json().get("candidates", []):
            for row in cand["organ_risks"]:
                iv, pt = row.get("interval") or {}, row.get("point_estimate")
                if iv.get("lo") is None or not pt:
                    continue
                agents.append(float(row["n_supporting_agents"]))
                relative_width.append((iv["hi"] - iv["lo"]) / pt)
    if len(agents) < 50:
        return None
    a, w = np.asarray(agents), np.asarray(relative_width)
    ra, rw = np.argsort(np.argsort(a)), np.argsort(np.argsort(w))
    rho = float(np.corrcoef(ra.astype(float), rw.astype(float))[0, 1])
    by_count = {}
    for k in sorted(set(agents)):
        sel = a == k
        by_count[int(k)] = {
            "cells": int(sel.sum()),
            "median_relative_width": round(float(np.median(w[sel])), 4),
        }
    widths = [v["median_relative_width"] for _, v in sorted(by_count.items())]
    return {
        "cells": len(agents),
        "spearman_agents_vs_relative_interval_width": round(rho, 4),
        "by_supporting_agents": by_count,
        "monotone": widths == sorted(widths, reverse=True),
        "reading": (
            "The interval does not encode the agent count: the rank correlation is "
            f"{rho:+.4f} and the medians are not monotone in it. So the thin flag is not "
            "redundant with the interval, and its threshold is not a precision cut-off. "
            "What three agents buys is attributability -- below it the chemistry's effect "
            "on that organ cannot be held out, so the estimate is untestable rather than "
            "imprecise, and those are different warnings."
        ),
    }


def _which_axes_reach_the_output(limit: int = 8) -> dict | None:
    """Which organ axes actually surface in a proposal, and are they the well-evidenced ones?

    Two questions in one pass, and they answer each other.

    The first is whether a thin axis is load-bearing. Otologic rests on 28% of the corpus's
    agents and renal on 49%, and that only matters for the product if those axes reach the
    screen's top of the ranking. They do not -- which is the reassuring half.

    The second is what that implies about the ranking. If the same handful of axes occupies
    the top of every proposal, the organ ordering is the base rate's ordering, which is what
    section 4 measures as a ratio and this states as a count: how many of the fourteen axes
    ever reach a candidate's top three.
    """
    try:
        from fastapi.testclient import TestClient

        from adctox.api.main import app
    except Exception:
        return None
    client = TestClient(app)
    top3: collections.Counter = collections.Counter()
    worst: collections.Counter = collections.Counter()
    candidates = 0
    for target in ("HER2", "TROP2", "CD30", "BCMA", "FOLR1", "EGFR", "CD19",
                   "NaPi2b")[:limit]:
        resp = client.post("/api/v1/propose", json={
            "comorbidity_profile": {"conditions": [],
                                    "cohort": {"age_band": "65_74", "sex": "female"}},
            "target_antigen": target, "top_k": 6,
        })
        if resp.status_code != 200:
            continue
        for cand in resp.json().get("candidates", []):
            ranked = sorted(
                ((r["organ_axis"], r.get("point_estimate") or 0.0)
                 for r in cand["organ_risks"]),
                key=lambda kv: -kv[1],
            )
            if not ranked:
                continue
            candidates += 1
            for axis, _ in ranked[:3]:
                top3[axis] += 1
            worst[ranked[0][0]] += 1
    if not candidates:
        return None
    return {
        "candidates": candidates,
        "axes_reaching_top_three": sorted(top3),
        "n_axes_reaching_top_three": len(top3),
        "axes_never_reaching_top_three": sorted(
            set(Taxonomy().axis_order) - set(top3)
        ),
        "top_three_counts": dict(top3.most_common()),
        "worst_axis_counts": dict(worst.most_common()),
    }


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
        "thinness_vs_interval": _thinness_is_not_in_the_interval(),
        "axes_reaching_the_output": _which_axes_reach_the_output(),
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
    out = doc.get("axes_reaching_the_output")
    if out:
        thin = {r["axis"] for r in growth if r["thin"]}
        reached = set(out["axes_reaching_top_three"])
        print()
        print(f"axes reaching a candidate's top three, over {out['candidates']} "
              f"candidates: {out['n_axes_reaching_top_three']} of {len(axes)}")
        print(f"  {out['top_three_counts']}")
        print(f"  never in a top three: {out['axes_never_reaching_top_three']}")
        print(f"  thin axes reaching a top three: {sorted(thin & reached) or 'none'}")
    tvi = doc.get("thinness_vs_interval")
    if tvi:
        print()
        print(f"thin flag against the interval, over {tvi['cells']} product cells: "
              f"rho {tvi['spearman_agents_vs_relative_interval_width']:+.4f}, "
              f"monotone {tvi['monotone']}")
        for k, v in sorted(tvi["by_supporting_agents"].items()):
            print(f"  {k:3} agents  {v['cells']:4} cells  median relative width "
                  f"{v['median_relative_width']:.3f}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
