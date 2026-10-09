"""Tests for holding an agent out of the fit, which inverse retrieval depends on.

The inverse-retrieval evaluation asks whether the system proposes an approved ADC's own
design given only its target. A model that has seen that drug's pivotal trials already
knows what its chemistry does to its population, so the evaluation is worthless without a
clean hold-out -- which is why it costs fifteen refits rather than one.

The subtle part is not dropping the agent, it is dropping what the agent contaminated.
NCT03529110 is a trastuzumab deruxtecan versus trastuzumab emtansine head-to-head, so
removing one arm leaves a comparator whose trial-level intercept was fitted partly from the
arm just removed. `splits.py` documents that leak for cross-validation and measured it
flattering the family and mechanism folds; it would flatter retrieval in exactly the place
retrieval is hardest, since the two agents share a target as well as a trial.
"""

from __future__ import annotations

import pathlib

import pandas as pd
import pytest

import adctox.model.dataset as ds
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
HEAD_TO_HEAD = "NCT03529110"


@pytest.fixture(scope="module")
def axes() -> list[str]:
    return list(default_taxonomy().axis_order)


def test_dropping_an_agent_removes_it(axes) -> None:
    full = ds.load(PROCESSED, axes, kind="other")
    held = ds.load(PROCESSED, axes, kind="other",
                   drop_agents=["trastuzumab_emtansine"])
    assert "trastuzumab_emtansine" in full.agents
    assert "trastuzumab_emtansine" not in held.agents
    assert len(held.agents) == len(full.agents) - 1
    assert held.n_arms < full.n_arms
    assert held.n_cells < full.n_cells


def test_dropping_an_agent_also_drops_the_trials_it_shared(axes) -> None:
    """The load-bearing case, and it runs in both directions because the leak is
    symmetric: whichever arm of the head-to-head is held out, the other one's intercept
    carries information from it."""
    arms = pd.read_parquet(PROCESSED / "arms.parquet")
    pair = arms[arms["nct_id"] == HEAD_TO_HEAD]["agent"].dropna().unique().tolist()
    assert len(pair) == 2, (
        f"{HEAD_TO_HEAD} is supposed to be a two-agent head-to-head; got {pair}"
    )
    for agent in pair:
        held = ds.load(PROCESSED, axes, kind="other", drop_agents=[agent])
        assert HEAD_TO_HEAD not in held.trials, (agent, HEAD_TO_HEAD)
        # And the comparator survives as an agent -- only its shared trial is gone.
        other = [a for a in pair if a != agent][0]
        assert other in held.agents, (agent, other)


def test_a_single_arm_trial_is_not_dropped_for_sharing_a_sentinel(axes) -> None:
    """128 arms come from single-arm trials and are collapsed onto a shared sentinel index
    in the model matrix. Treating that sentinel as a shared trial would delete every
    single-arm study whenever any agent was held out -- the same mistake `splits.py` found
    in its own fold construction, where it discarded 1,980 arm-folds."""
    full = ds.load(PROCESSED, axes, kind="other")
    held = ds.load(PROCESSED, axes, kind="other",
                   drop_agents=["moxetumomab_pasudotox"])
    # Holding out one small agent must not take a large share of the corpus with it.
    assert held.n_arms > 0.8 * full.n_arms, (held.n_arms, full.n_arms)


def test_holding_out_every_agent_in_turn_leaves_a_fittable_corpus(axes) -> None:
    """A fold that leaves too few mechanisms or agents cannot be fitted, and discovering
    that fifteen refits into a four-hour run would be expensive."""
    full = ds.load(PROCESSED, axes, kind="other")
    for agent in full.agents:
        held = ds.load(PROCESSED, axes, kind="other", drop_agents=[agent])
        assert held.n_arms >= 20, (agent, held.n_arms)
        assert len(held.mechanisms) >= 3, (agent, held.mechanisms)
        assert len(held.agents) == len(full.agents) - 1, agent


def test_the_precedent_objective_can_have_an_agent_removed_from_it() -> None:
    """O3 rewards configurations clinical ADCs already use, and the agent being searched
    for is one of them. Without decrementing its components, a retrieval hit cannot be
    told from memory of the counts."""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import yaml

    from inverse_retrieval import decremented_design_space

    registry = yaml.safe_load(
        (ROOT / "conf" / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]
    base = yaml.safe_load(
        (ROOT / "conf" / "design_space.yaml").read_text(encoding="utf-8")
    )
    spec = registry["trastuzumab_emtansine"]
    adjusted = decremented_design_space(spec)
    for section, key in (
        ("payloads", spec["payload"]),
        ("linkers", spec["linker_type"]),
        ("conjugation_dar", spec["conjugation"]),
    ):
        before = base[section][key].get("clinical_adcs")
        after = adjusted[section][key].get("clinical_adcs")
        if before:
            assert after == before - 1, (section, key, before, after)
    # And the original document is untouched, so one agent's adjustment cannot leak into
    # the next agent's run.
    assert base["payloads"][spec["payload"]]["clinical_adcs"] == yaml.safe_load(
        (ROOT / "conf" / "design_space.yaml").read_text(encoding="utf-8")
    )["payloads"][spec["payload"]]["clinical_adcs"]


def test_a_smoke_run_is_marked_as_not_a_result() -> None:
    """A two-agent run at 80 draws reported "informative slots 1/7, chance 1.30, excess
    -0.30, p 0.77". That reads like a finding and is a statement about an unconverged
    sampler, so the artefact carries `is_result` and a reason rather than leaving the
    distinction in a log line nobody keeps."""
    import json
    import subprocess
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "ir.json"
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "inverse_retrieval.py"),
             "--agents", "trastuzumab_emtansine", "--warmup", "60", "--samples", "60",
             "--out", str(out)],
            capture_output=True, text=True, cwd=ROOT,
        )
        assert r.returncode == 0, r.stderr[-1500:]
        d = json.loads(out.read_text(encoding="utf-8"))
    assert d["is_result"] is False
    assert d["why_not_a_result"]
    assert d["warmup"] == 60 and d["samples"] == 60


def test_the_uninformative_slots_are_identified_from_the_feasible_set() -> None:
    """The correction that changes how this evaluation reads. The plan's headline was slot
    accuracy out of 7 against a nominal chance of 2.03, but measured against what the
    enumerator can actually build for a target, isotype matches 89% of feasible candidates
    and masking 91% -- IgG1 and no-masking dominate the legal space. Counting them inflates
    the result: trastuzumab emtansine scores 4 of 6 all-slots and 1 of 3 informative, with
    a chance expectation of 0.51 rather than 2.03."""
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from inverse_retrieval import SLOTS, UNINFORMATIVE_CHANCE, chance_rate

    # A feasible set where isotype and masking are near-constant, as they are in practice.
    spec = {"payload": "DM1", "linker_type": "SMCC", "conjugation": "lysine",
            "dar": 3.5, "isotype": "IgG1"}
    feasible = [
        {"payload": p, "linker": "SMCC", "conjugation": "lysine", "dar": 3.5,
         "isotype": "IgG1", "masking": "none"}
        for p in ("DM1", "DM4", "MMAE", "MMAF", "DXd", "SN-38", "calicheamicin")
    ]
    chance = chance_rate(feasible, spec)
    assert chance["isotype"] >= UNINFORMATIVE_CHANCE
    assert chance["masking"] >= UNINFORMATIVE_CHANCE
    assert chance["payload"] < UNINFORMATIVE_CHANCE
    informative = [s for s in SLOTS if chance[s] < UNINFORMATIVE_CHANCE]
    assert "payload" in informative
    assert "isotype" not in informative and "masking" not in informative
