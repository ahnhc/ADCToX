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
# The 18 agents `conf/adc_registry.yaml` held before the literature stem sweep, at commit
# 0dfecc8. Pinned as a literal rather than read from git history, so the ablation's first
# stage is reproducible from a clean clone without a revision walk -- and so that a later
# edit to the registry cannot silently change what "before" means.
ORIGINAL_REGISTRY_AGENTS = frozenset({
    "belantamab_mafodotin", "brentuximab_vedotin", "datopotamab_deruxtecan",
    "enfortumab_vedotin", "gemtuzumab_ozogamicin", "inotuzumab_ozogamicin",
    "loncastuximab_tesirine", "mirvetuximab_soravtansine", "moxetumomab_pasudotox",
    "patritumab_deruxtecan", "pivekimab_sunirine", "polatuzumab_vedotin",
    "sacituzumab_govitecan", "telisotuzumab_vedotin", "tisotumab_vedotin",
    "trastuzumab_deruxtecan", "trastuzumab_duocarmazine", "trastuzumab_emtansine",
})

MIN_AGENTS_FOR_FOLD = 3
# Design coefficients in the shipped specification: mu_axis, the mechanism and cleavability
# interactions, and the four scalars. Fixed rather than counted from a fit, because the
# ratio is a property of the specification and must be comparable across corpora.
DESIGN_PARAMETERS = 100


def _frames(
    path: pathlib.Path,
    agents: set[str] | None = None,
    restrict_all: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load a corpus, optionally keeping only arms of the given agents.

    The middle stage -- registry arms plus literature arms for agents already present -- was
    a separate directory on disk, produced once by a path no flag reproduces. It went stale
    the moment the merge gained a column, and the ablation then compared a filtered corpus
    against an unfiltered one and reported the second stage as *losing* thirteen arms. All
    three stages are now derived from the full union here, which is what makes the nesting
    claim true by construction rather than by a check.
    """
    arms = pd.read_parquet(path / "arms.parquet")
    obs = pd.read_parquet(path / "observations.parquet")
    if agents is not None:
        if restrict_all:
            # Every arm must be one of the named agents. This is what the agent-list
            # stages need, and the clause below is not: on the registry frame `source` is
            # null for every row, so "keep a registry arm or an arm of a named agent" keeps
            # everything and the filter was silently a no-op -- the first two stages came
            # out identical.
            mask = arms["agent"].isin(agents)
        else:
            # Keep every registry arm plus the literature arms of the named agents, which
            # is what separates "more arms of agents we had" from "arms of new agents".
            mask = (
                arms["source"].isna() if "source" in arms else pd.Series(
                    True, index=arms.index
                )
            ) | arms["agent"].isin(agents)
        arms = arms[mask].reset_index(drop=True)
        obs = obs[obs["arm_key"].isin(set(arms["arm_key"]))].reset_index(drop=True)
    return arms, obs


def describe(
    path: pathlib.Path, axes: list[str], agents: set[str] | None = None,
    restrict_all: bool = False,
) -> dict:
    arms, obs = _frames(path, agents, restrict_all)
    data = ds.build(arms, obs, axes, kind="other")
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
        # The ratio the model card quotes. Derived rather than typed, because a figure
        # computed in prose is a figure the number guard cannot trace -- and the previous
        # value traced only by coincidence, 4.48 happening to appear elsewhere in the pool.
        "design_parameters": DESIGN_PARAMETERS,
        "cells_per_design_parameter": round(
            len(data.agents) * len(data.axes) / DESIGN_PARAMETERS, 2
        ),
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
    registry = ROOT / "data" / "processed"
    full = registry / "with_literature_final"
    if not (full / "arms.parquet").exists():
        print(f"missing {full}; run `make pmc-merge`", file=sys.stderr)
        return 1

    # Four stages, not three, because the first one was mislabelled.
    #
    # Attribution matches a ClinicalTrials.gov event group against the *names and aliases*
    # in `conf/adc_registry.yaml`, and 17 of that file's 35 agents were found by the
    # literature's payload-linker stem sweep. So "registry only" with the current registry
    # is not "before the literature work": it is registry data read with a literature-
    # derived agent list, and it attributes 894 event groups where the original 18-agent
    # list attributed 781.
    #
    # That makes the literature's contribution two separate things, and they were being
    # reported as one. Naming an agent turns its existing ClinicalTrials.gov records from
    # unattributable into usable; extracting its arms from papers adds new records. The
    # first is free of the literature's reporting selection entirely, which is the opposite
    # of what section 5g measures about the second.
    original = ORIGINAL_REGISTRY_AGENTS
    registry_agents = set(
        pd.read_parquet(registry / "arms.parquet")["agent"].dropna().unique()
    )
    stages = {
        "ctgov_original_agent_list": (registry, original, True),
        "ctgov_literature_agent_list": (registry, None, False),
        "plus_literature_arms": (full, registry_agents, False),
        "plus_literature_agents": (full, None, False),
    }
    # A fifth stage, where the frames exist: the corpus merged with the hand-transcribed
    # database. It is the first stage that is not a reading of ClinicalTrials.gov plus the
    # open-access literature, and the one that crosses the plan's identification floor.
    # Added conditionally because the workbook is not redistributed, so a clean clone has
    # four stages and the table shortens rather than failing.
    merged = ROOT / "data" / "processed" / "with_atlas"
    if (merged / "arms.parquet").exists():
        stages["plus_transcribed"] = (merged, None, False)
    described: dict[str, dict] = {}
    for name, (path, agents, restrict) in stages.items():
        described[name] = describe(path, axes, agents, restrict)

    # The nesting claim, checked. A stage that is not a superset of the one before it makes
    # the ablation uninterpretable, because a difference could then come from arms that
    # were dropped rather than from arms that were added.
    #
    # Two arm counts, reported separately because they differ by 77 arms at the first step
    # and conflating them is how this table gets misread. The corpus count is what the
    # merge wrote. The grid count is what the fit sees, and three filters stand between
    # them: an attributable agent, a denominator of at least 30, and a conventional
    # conjugate. A fourth was added later -- an arm enters a table's grid only if it
    # published that table -- and it accounts for 5 of the 77; the pre-existing three
    # account for the rest. The nesting verdict is about the corpus, which is the right
    # level for it: a stage that drops a corpus arm makes the ablation uninterpretable.
    nesting: list[dict] = []
    order = [n for n in stages if n in described]
    for prev, cur in zip(order, order[1:]):
        a = set(_frames(*stages[prev])[0]["arm_key"])
        b = set(_frames(*stages[cur])[0]["arm_key"])
        nesting.append({
            "from": prev, "to": cur,
            "corpus_arms_added": len(b - a),
            "corpus_arms_dropped": len(a - b),
            "grid_arms_added": described[cur]["n_arms"] - described[prev]["n_arms"],
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
        print(f"  {n['from']} -> {n['to']}: corpus +{n['corpus_arms_added']} arms, "
              f"-{n['corpus_arms_dropped']} dropped; "
              f"grid +{n['grid_arms_added']}  [{verdict}]")
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
