"""Is each design contrast estimated from agents on both sides of it?

A binary design feature needs agents at both of its levels, and the plan set that floor at
eight for linker cleavability -- the one design axis this report describes as "identified
comfortably", on the grounds that a binary needs fewer agents than a mechanism level.

Counted in agents, because design features are agent-level constants, the registry corpus
has **three** non-cleavable agents. Not eight. And all three are tubulin, so for every other
payload mechanism cleavability has no variation at all: `tau_cleav` on that corpus is an
effect estimated inside one mechanism and reported under a corpus-wide name.

So the floor was being checked against the wrong count. "Needs only 8 agents" is a statement
about the *minority* level, and a corpus can have 65 agents and 3 of them non-cleavable.
This measures the minority count for every categorical design feature, and the per-mechanism
breakdown beside it, because a contrast nested inside one mechanism is not a contrast
between mechanisms however many agents carry it.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.model import dataset as ds
from adctox.provenance import write_json
from adctox.taxonomy import Taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]

CORPORA = [
    ("registry", "data/processed"),
    ("expanded", "data/processed/with_literature_final"),
    ("merged", "data/processed/with_atlas"),
]

# The plan's floor for a binary design contrast, stated as agents. Read here as agents at the
# *minority* level, which is what the contrast actually rests on.
BINARY_AGENT_FLOOR = 8


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "design_balance.json")
    args = ap.parse_args()

    axes = list(Taxonomy().axis_order)
    corpora = {}
    for name, rel in CORPORA:
        path = ROOT / rel
        if not (path / "arms.parquet").exists():
            continue
        data = ds.load(path, axes, kind="other")
        # One value per agent: a design feature is an agent-level constant, so counting arms
        # would count trial populations and call them evidence about chemistry.
        cleavable_of_agent: dict[int, float] = {}
        mech_of_agent: dict[int, str] = {}
        for agent, cleav, mech in zip(data.arm_agent_idx, data.arm_cleavable,
                                      data.arm_mech_idx):
            cleavable_of_agent[int(agent)] = float(cleav)
            mech_of_agent[int(agent)] = data.mechanisms[int(mech)]

        values = np.array(list(cleavable_of_agent.values()))
        n_non, n_cleav = int((values == 0).sum()), int((values == 1).sum())
        minority = min(n_non, n_cleav)

        by_mech: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
        for agent, value in cleavable_of_agent.items():
            by_mech[mech_of_agent[agent]][0 if value == 0 else 1] += 1
        varying = [m for m, (a, b) in by_mech.items() if a and b]

        # DAR is the model's only continuous design feature, and its balance question is
        # different: not "are there agents on both sides" but "does it vary *inside* a
        # mechanism". If it does not, `b_dar` competes with a 14-parameter `mech_axis`
        # vector for the same information and is identified by nothing of its own.
        dar_of_agent: dict[int, float] = {}
        for agent, dar_c in zip(data.arm_agent_idx, data.arm_dar_c):
            dar_of_agent[int(agent)] = float(dar_c) + data.dar_mean
        dar_by_mech: dict[str, list[float]] = collections.defaultdict(list)
        for agent, value in dar_of_agent.items():
            dar_by_mech[mech_of_agent[agent]].append(value)
        all_dar = np.array(list(dar_of_agent.values()))
        grand = float(all_dar.mean())
        within = float(sum(
            float(((np.array(v) - np.mean(v)) ** 2).sum()) for v in dar_by_mech.values()
        ))
        between = float(sum(
            len(v) * (float(np.mean(v)) - grand) ** 2 for v in dar_by_mech.values()
        ))
        total = within + between

        corpora[name] = {
            "agents": len(values),
            "dar": {
                "median": round(float(np.median(all_dar)), 3),
                "within_mechanism_variance_share": (
                    round(within / total, 4) if total else None
                ),
                "by_mechanism": {
                    m: {"agents": len(v), "min": round(float(np.min(v)), 2),
                        "max": round(float(np.max(v)), 2),
                        "sd": round(float(np.std(v)), 3)}
                    for m, v in sorted(dar_by_mech.items())
                },
                "note": ("A low within-mechanism share means DAR carries mechanism "
                         "identity, and `mech_axis` already has 14 parameters for that, so "
                         "`b_dar` would be identified by nothing of its own."),
            },
            "cleavability": {
                "cleavable_agents": n_cleav,
                "non_cleavable_agents": n_non,
                "minority_agents": minority,
                "minority_share": round(minority / len(values), 4),
                "meets_binary_agent_floor": minority >= BINARY_AGENT_FLOOR,
                "by_mechanism": {m: {"non_cleavable": a, "cleavable": b}
                                 for m, (a, b) in sorted(by_mech.items())},
                "mechanisms_with_variation": sorted(varying),
                "n_mechanisms": len(by_mech),
                # A contrast present in one mechanism only is nested in it, whatever the
                # agent count: removing that mechanism removes the contrast.
                "nested_in_one_mechanism": len(varying) == 1,
            },
        }

    doc = {
        "binary_agent_floor": BINARY_AGENT_FLOOR,
        "corpora": corpora,
        "summary": {
            "dar_within_mechanism_share": {
                k: v["dar"]["within_mechanism_variance_share"] for k, v in corpora.items()
            },
            "corpora_meeting_the_floor": [
                k for k, v in corpora.items()
                if v["cleavability"]["meets_binary_agent_floor"]
            ],
            "corpora_where_cleavability_is_nested": [
                k for k, v in corpora.items()
                if v["cleavability"]["nested_in_one_mechanism"]
            ],
        },
    }
    write_json(args.out, doc)

    print(f"{'corpus':10} {'agents':>7} {'cleavable':>10} {'non-cleav':>10} "
          f"{'minority':>9} {'floor':>6} {'mechanisms varying':>20}")
    for name, v in corpora.items():
        c = v["cleavability"]
        print(f"{name:10} {v['agents']:>7} {c['cleavable_agents']:>10} "
              f"{c['non_cleavable_agents']:>10} {c['minority_agents']:>9} "
              f"{'yes' if c['meets_binary_agent_floor'] else 'NO':>6} "
              f"{len(c['mechanisms_with_variation']):>3} of {c['n_mechanisms']:<3}"
              f"{'  NESTED' if c['nested_in_one_mechanism'] else ''}")
    print()
    for name, v in corpora.items():
        c = v["cleavability"]
        print(f"{name}: " + ", ".join(
            f"{m} {d['non_cleavable']}/{d['non_cleavable'] + d['cleavable']}"
            for m, d in c["by_mechanism"].items()) + "   (non-cleavable / agents)")
    print()
    print("DAR, the only continuous design feature: does it vary inside a mechanism?")
    for name, v in corpora.items():
        d = v["dar"]
        print(f"  {name:10} median {d['median']:.2f}  within-mechanism variance share "
              f"{d['within_mechanism_variance_share']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
