"""At which granularity does the identification ratio recede, and at which does it improve?

The plan's central structural claim is that the resolution which would improve prediction
recedes as fast as it is approached: each new agent brings a new payload, so tripling the
corpus leaves identifying-cells-per-design-parameter flat. Its table put that at 2.12, 2.91
and 2.84 across corpora of 17, 32 and 54 agents.

**Measured over five stages, that mechanism is wrong and the conclusion survives.** The
payload-level ratio runs 1.78, 2.20, 2.50, 2.13, 2.91 as the agents run 16, 22, 25, 32, 64:
a 1.63x gain for a 4x corpus, so `recedes` comes back empty. The level approaches its floor
at a rate that would need something over a thousand agents to reach it, against the roughly
370 that have ever entered the clinic. Out of reach because the field is finite.

Two of those three rows were projections. The 54-agent corpus was measured not to exist --
the ceiling is 32 agents, 31 of which publish an any-grade column -- and the payload
vocabulary was projected to reach 12 classes at the second step and 20 at the third. It
reaches 16 payload identities and 8 families at 31 agents.

Measured, the claim is true at one granularity and false at the two coarser ones. The ratio
is computed the plan's own way: identifying cells over `(levels - 1) x axes`, which
reproduces its 4.25, 6.40 and 9.00 for the mechanism level exactly.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adctox.model.dataset import build
import corpus_ablation as _ablation
from adctox.provenance import write_json
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]
# The plan's threshold for identifying a level-by-axis interaction.
IDENTIFICATION_FLOOR = 8.0
# Shared with `corpus_ablation.py`, which is where it is defined and
# justified; imported so the two scripts cannot drift apart about what
# "before the literature work" means.
ORIGINAL_REGISTRY_AGENTS = _ablation.ORIGINAL_REGISTRY_AGENTS


def _stage(
    path: pathlib.Path, axes: list[str], keep: set[str] | None,
    restrict_all: bool = False,
):
    """One corpus stage, sharing `corpus_ablation.py`'s definitions.

    The two scripts must not disagree about what "registry only" means. The ablation found
    that the phrase was ambiguous -- attribution uses the registry's *names*, and 17 of the
    35 came from the literature's stem sweep -- so both now carry the same four stages and
    the same filter semantics, including that `restrict_all` is what the agent-list stages
    need: on the registry frame `source` is null for every row, so "keep a registry arm or
    an arm of a named agent" keeps everything.
    """
    arms = pd.read_parquet(path / "arms.parquet")
    obs = pd.read_parquet(path / "observations.parquet")
    if keep is not None:
        if restrict_all:
            mask = arms["agent"].isin(keep)
        else:
            mask = (
                arms["source"].isna() if "source" in arms
                else pd.Series(True, index=arms.index)
            ) | arms["agent"].isin(keep)
        arms = arms[mask].reset_index(drop=True)
        obs = obs[obs["arm_key"].isin(set(arms["arm_key"]))].reset_index(drop=True)
    data = build(arms, obs, axes, kind="other")
    inc = set(data.agents)
    payloads = sorted(
        {p for p in arms.loc[arms["agent"].isin(inc), "payload"].dropna()}
    )
    return data, payloads


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=pathlib.Path,
                    default=ROOT / "data" / "processed")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "granularity_ratio.json")
    args = ap.parse_args()

    axes = list(default_taxonomy().axis_order)
    full = args.processed / "with_literature_final"
    registry_agents = set(
        pd.read_parquet(args.processed / "arms.parquet")["agent"].dropna().unique()
    )
    stages = {
        "ctgov_original_agent_list": (args.processed, ORIGINAL_REGISTRY_AGENTS, True),
        "ctgov_literature_agent_list": (args.processed, None, False),
        "plus_literature_arms": (full, registry_agents, False),
        "plus_literature_agents": (full, None, False),
    }
    # The fifth stage, kept in step with `corpus_ablation.py` by a test: two scripts that
    # disagree about what a stage is produce two tables the report presents as one. Added
    # conditionally, because the hand-transcribed workbook is not redistributed and a clean
    # clone has four stages.
    merged = ROOT / "data" / "processed" / "with_atlas"
    if (merged / "arms.parquet").exists():
        stages["plus_transcribed"] = (merged, None, False)

    rows = []
    for name, (path, keep, restrict) in stages.items():
        data, payloads = _stage(path, axes, keep, restrict)
        agents = data.n_contributing_agents
        identifying = agents * len(axes)
        levels = {
            "payload_identity": len(payloads),
            "payload_family": len(data.families),
            "mechanism": len(data.mechanisms),
        }
        row = {"stage": name, "agents": agents, "identifying_cells": identifying,
               "levels": levels, "ratio": {}}
        for level, k in levels.items():
            params = max(k - 1, 1) * len(axes)
            row["ratio"][level] = round(identifying / params, 2)
        rows.append(row)

    first, last = rows[0], rows[-1]
    change = {
        level: round(last["ratio"][level] / first["ratio"][level], 2)
        for level in first["ratio"]
    }
    summary = {
        "identification_floor": IDENTIFICATION_FLOOR,
        # The claim being refuted, recorded beside the refutation. The plan projected the
        # mechanism-level ratio at corpora of 17, 32 and 54 agents assuming the mechanism
        # count would grow 5 -> 6 -> 7 with them. It stayed at 5, and the 54-agent corpus
        # was measured not to exist.
        "plan_projection_mechanism_level": {
            "n17_k5": round(17 * 14 / ((5 - 1) * 14), 2),
            "n32_k6": round(32 * 14 / ((6 - 1) * 14), 2),
            "n54_k7": round(54 * 14 / ((7 - 1) * 14), 2),
        },
        # Named for the stages it actually spans, not for a stage that used to be last. It
        # read `ratio_change_registry_to_expanded` while comparing the registry corpus to
        # whatever the final stage was, and the final stage changed: the payload-level
        # change it reports went from 1.20 against the 32-agent corpus to 1.63 against the
        # 64-agent one, which is the difference between "recedes" and "approaches too
        # slowly". A key named after a moving target is the same defect as a sentence
        # beside a regenerated number; see negative result 38.
        "ratio_change_first_to_last_stage": change,
        "first_stage": rows[0]["stage"],
        "last_stage": rows[-1]["stage"],
        "levels_that_clear_the_floor": [
            level for level, v in last["ratio"].items() if v >= IDENTIFICATION_FLOOR
        ],
        # "Recedes" is the claim that a level's ratio does not improve as the corpus grows,
        # which is result 6's stated mechanism. 1.25 is the floor for calling an improvement
        # real; below it the ratio is flat within the noise of a stage boundary.
        "recedes_threshold": 1.25,
        "recedes": [level for level, v in change.items() if v < 1.25],
    }

    print(f"  {'stage':24s} {'agents':>7s} {'ident':>6s} "
          + " ".join(f"{k:>18s}" for k in first["ratio"]))
    for r in rows:
        print(f"  {r['stage']:24s} {r['agents']:7d} {r['identifying_cells']:6d} "
              + " ".join(
                  f"{r['ratio'][k]:8.2f} (k={r['levels'][k]:2d})" for k in r["ratio"]
              ))
    print()
    for k, v in summary.items():
        print(f"  {k:36s} {v}")
    write_json(args.out, {"summary": summary, "stages": rows})
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
