"""Emit the corpus ablation as an artefact, so the report can quote it without typing.

The plan asks for an ablation over corpus size -- registry only, plus literature arms,
plus literature agents -- and the three corpora nest exactly, which is what makes the
comparison interpretable: every arm in the smaller corpus is in the larger one, so a
difference between two fits is attributable to what was added rather than to drift in
what was kept. That nesting is checked here rather than assumed.

The row that governs the whole project is the identifying-cell count. Design features are
agent-level constants, so a corpus identifies a design coefficient with `agents x axes`
cells and not with its total. Doubling the arms of agents already present adds nothing to
that row; adding agents is the only thing that does.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import adctox.model.dataset as ds  # noqa: E402
from adctox.provenance import stamp  # noqa: E402
from adctox.taxonomy import default_taxonomy  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIN_AGENTS_FOR_FOLD = 3


def describe(path: pathlib.Path, axes: list[str]) -> dict:
    data = ds.load(path, axes, kind="other")
    per_mech: dict[str, set[int]] = {}
    arms_per_mech: dict[str, int] = {}
    for mi, ai in zip(data.arm_mech_idx, data.arm_agent_idx):
        name = data.mechanisms[int(mi)]
        per_mech.setdefault(name, set()).add(int(ai))
        arms_per_mech[name] = arms_per_mech.get(name, 0) + 1
    mechanisms = {
        name: {
            "agents": len(agents),
            "arms": arms_per_mech[name],
            "viable_fold": len(agents) >= MIN_AGENTS_FOR_FOLD,
        }
        for name, agents in sorted(per_mech.items())
    }
    observed = int((data.status == 0).sum())
    censored = int(len(data.censored_idx))
    return {
        "summary": data.summary(),
        # The share of cells that are censored rather than observed, which turned out to
        # be the thing that decides whether literature arms help. A registry arm reports
        # most of its organs; a paper's AE table reports a handful, so the other ten or
        # eleven axes arrive as censored cells -- and for 83% of paper arms the censoring
        # boundary is an *upper* bound derived from the minimum printed rate rather than a
        # stated cut. Thousands of cells are therefore told "below X" with X too large.
        "observed_share": observed / int(data.n_cells),
        "censored_share": censored / int(data.n_cells),
        "n_agents": len(data.agents),
        "n_arms": int(data.n_arms),
        "n_cells": int(data.n_cells),
        "n_axes": len(data.axes),
        "identifying_cells": len(data.agents) * len(data.axes),
        "n_observed": int((data.status == 0).sum()),
        "n_censored": int(len(data.censored_idx)),
        "mechanisms": mechanisms,
        "n_viable_folds": sum(1 for m in mechanisms.values() if m["viable_fold"]),
        "viable_folds": sorted(
            n for n, m in mechanisms.items() if m["viable_fold"]
        ),
        "agents": list(data.agents),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "corpus_ablation.json")
    args = ap.parse_args()

    axes = list(default_taxonomy().axis_order)
    stages = {
        "registry_only": ROOT / "data" / "processed",
        "plus_literature_arms": ROOT / "data" / "processed" / "with_literature",
        "plus_literature_agents": ROOT / "data" / "processed" / "with_literature_final",
    }
    described: dict[str, dict] = {}
    for name, path in stages.items():
        if not (path / "arms.parquet").exists():
            print(f"missing {path}; skipping {name}", file=sys.stderr)
            continue
        described[name] = describe(path, axes)

    # The nesting claim, checked. A stage that is not a superset of the one before it makes
    # the ablation uninterpretable, because a difference could then come from arms that
    # were dropped rather than from arms that were added.
    nesting: list[dict] = []
    order = [n for n in stages if n in described]
    for prev, cur in zip(order, order[1:]):
        a = set(pd.read_parquet(stages[prev] / "arms.parquet")["arm_key"])
        b = set(pd.read_parquet(stages[cur] / "arms.parquet")["arm_key"])
        nesting.append({
            "from": prev, "to": cur,
            "arms_added": len(b - a),
            "arms_dropped": len(a - b),
            "is_superset": not (a - b),
        })

    print(f"  {'stage':26s} {'agents':>7s} {'arms':>6s} {'cells':>7s} "
          f"{'ident':>6s} {'folds':>6s}")
    for name in order:
        d = described[name]
        print(f"  {name:26s} {d['n_agents']:7d} {d['n_arms']:6d} {d['n_cells']:7d} "
              f"{d['identifying_cells']:6d} {d['n_viable_folds']:6d}")
    print()
    for n in nesting:
        verdict = "nested" if n["is_superset"] else "NOT NESTED"
        print(f"  {n['from']} -> {n['to']}: +{n['arms_added']} arms, "
              f"-{n['arms_dropped']} dropped  [{verdict}]")
    print()
    for name in order:
        d = described[name]
        print(f"  {name}: viable folds {d['viable_folds']}")

    out = {
        "provenance": stamp(),
        "min_agents_for_fold": MIN_AGENTS_FOR_FOLD,
        "stages": described,
        "nesting": nesting,
        "all_nested": all(n["is_superset"] for n in nesting),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
