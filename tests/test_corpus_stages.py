"""The ablation's four stages, and the invariant that keeps the first one honest.

"ClinicalTrials.gov only" was computed with the current 35-agent registry, 17 of whose
agents were found by the literature's payload-linker stem sweep. So the stage that was
supposed to be "before the literature work" was already using its results, and the
decomposition reported two contributions as one:

* naming an agent turns its existing ClinicalTrials.gov records from unattributable into
  usable -- 6 agents and 84 identifying cells, at no cost to the observed share;
* extracting its arms from papers adds records that carry the literature's reporting
  selection -- 42 identifying cells, and the observed share falls from 86.6% to 67.9%.

The first stage is pinned against the figures this report published for it, which is what
makes the correction a relabelling rather than a revision: 16 agents, 285 arms, 3,990 cells,
224 identifying cells, two viable folds. If a registry edit ever changes those, the stage no
longer means what the report says it means and this fails.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTEFACT = ROOT / "artifacts" / "corpus_ablation.json"
SPEC = importlib.util.spec_from_file_location(
    "corpus_ablation", ROOT / "scripts" / "corpus_ablation.py"
)
ablation = importlib.util.module_from_spec(SPEC)
sys.modules["corpus_ablation"] = ablation
SPEC.loader.exec_module(ablation)


@pytest.fixture(scope="module")
def stages() -> dict:
    if not ARTEFACT.exists():
        pytest.skip("run `make corpus-ablation`")
    return json.loads(ARTEFACT.read_text(encoding="utf-8"))["stages"]


def test_the_original_agent_list_is_the_one_the_report_published(stages) -> None:
    first = stages["ctgov_original_agent_list"]
    assert first["n_agents"] == 16, first
    assert first["n_arms"] == 285, first
    assert first["n_cells"] == 3990, first
    assert first["identifying_cells"] == 224, first
    assert first["n_viable_folds"] == 2, first
    assert 0.85 < first["observed_share"] < 0.87, first


def test_the_original_list_is_pinned_and_not_read_from_the_registry(stages) -> None:
    """Read from the current registry it would grow with it, and "before" would move every
    time an agent was added. 18 keys, from commit 0dfecc8."""
    assert len(ablation.ORIGINAL_REGISTRY_AGENTS) == 18
    import yaml

    current = yaml.safe_load(
        (ROOT / "conf" / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]
    assert len(current) > 30, "the registry no longer has the agents this contrasts with"
    assert ablation.ORIGINAL_REGISTRY_AGENTS <= set(current), (
        sorted(ablation.ORIGINAL_REGISTRY_AGENTS - set(current))
    )


def test_naming_the_agents_costs_nothing_and_extracting_the_arms_costs_the_share(
    stages,
) -> None:
    """The finding, as an invariant. The two contributions are opposite in kind and the
    decomposition exists to keep them apart."""
    a = stages["ctgov_original_agent_list"]
    b = stages["ctgov_literature_agent_list"]
    c = stages["plus_literature_arms"]

    # Naming: identifying cells up, observed share flat.
    assert b["identifying_cells"] - a["identifying_cells"] >= 50
    assert abs(b["observed_share"] - a["observed_share"]) < 0.02
    # Extracting: fewer identifying cells bought, and the share collapses.
    assert c["identifying_cells"] - b["identifying_cells"] < (
        b["identifying_cells"] - a["identifying_cells"]
    )
    assert b["observed_share"] - c["observed_share"] > 0.1


def test_the_third_mechanism_fold_opens_before_any_paper_arm(stages) -> None:
    """This report credited the third fold to the literature arms. It opens at the
    agent-list stage, on ClinicalTrials.gov records already on disk."""
    a = stages["ctgov_original_agent_list"]["mechanisms"]
    b = stages["ctgov_literature_agent_list"]["mechanisms"]
    assert a["dna_crosslink"]["viable_fold"] is False, a["dna_crosslink"]
    assert b["dna_crosslink"]["viable_fold"] is True, b["dna_crosslink"]
    assert b["dna_crosslink"]["agents"] >= 3


def test_the_stages_nest(stages) -> None:
    """A stage that drops a corpus arm makes the comparison uninterpretable, because a
    difference could then come from what left rather than from what arrived."""
    doc = json.loads(ARTEFACT.read_text(encoding="utf-8"))
    assert doc["all_nested"], doc["nesting"]
    for step in doc["nesting"]:
        assert step["corpus_arms_dropped"] == 0, step


def test_the_exclusions_are_measured_and_not_just_named() -> None:
    """Nine system-organ classes never reach an axis, each with a one-word reason. They
    drop 9.3% of registry rows and 4.7% of the patient mass, which makes them the largest
    discretionary decision in the corpus -- so the artefact records what is in each bucket
    and the reason beside it, rather than leaving the reason to be taken on trust.

    Psychiatric is three quarters of the excluded patient mass and is dominated by insomnia,
    anxiety and depression. That is what makes `not_organ_attributable` hold for it, and it
    is checkable only because the terms are recorded.
    """
    artefact = ROOT / "artifacts" / "axis_composition.json"
    if not artefact.exists():
        pytest.skip("run `make axis-composition`")
    doc = json.loads(artefact.read_text(encoding="utf-8"))
    summary, excluded = doc["summary"], doc["excluded"]

    assert 0.05 < summary["excluded_share_of_rows"] < 0.15, summary
    assert 0.02 < summary["excluded_share_of_patients"] < 0.10, summary
    # Every bucket names a reason, or the reason is not auditable.
    for e in excluded:
        assert e["reason"], e["soc"]
        assert e["top_terms"], e["soc"]
    # Psychiatric dominates the mass, and what is in it is what justifies dropping it.
    psych = next(e for e in excluded if "psychiatric" in e["soc"])
    assert psych["patients_affected"] / summary["excluded_patients_affected"] > 0.5
    terms = {t["term"] for t in psych["top_terms"]}
    assert {"insomnia", "anxiety", "depression"} <= terms, terms


def test_the_granularity_stages_match_the_ablation_s() -> None:
    """Two scripts must not disagree about what "before the literature work" means. The
    ablation found the phrase ambiguous; both now carry the same four stages."""
    artefact = ROOT / "artifacts" / "granularity_ratio.json"
    if not (artefact.exists() and ARTEFACT.exists()):
        pytest.skip("run `make granularity-ratio corpus-ablation`")
    gr = json.loads(artefact.read_text(encoding="utf-8"))
    ab = json.loads(ARTEFACT.read_text(encoding="utf-8"))
    assert [r["stage"] for r in gr["stages"]] == list(ab["stages"]), (
        [r["stage"] for r in gr["stages"]], list(ab["stages"])
    )
    for row in gr["stages"]:
        assert row["agents"] == ab["stages"][row["stage"]]["n_agents"], row["stage"]
        assert (
            row["identifying_cells"]
            == ab["stages"][row["stage"]]["identifying_cells"]
        ), row["stage"]


def test_the_ablation_table_grows_a_row_when_a_stage_is_added() -> None:
    """The table was hand-typed, and a hand-typed table does not grow a row.

    A fifth corpus stage arrived -- the hand-transcribed database -- and the four-stage
    table in section 4.3 would have gone on describing four. It is generated from
    `corpus_ablation.json` now, so the stages in the artefact and the rows in the report
    cannot disagree.
    """
    import json
    import pathlib
    import sys

    root = pathlib.Path(__file__).resolve().parents[1]
    artefact = root / "artifacts" / "corpus_ablation.json"
    if not artefact.exists():
        return
    sys.path.insert(0, str(root / "scripts"))
    import sync_report_numbers as srn

    doc = json.loads(artefact.read_text(encoding="utf-8"))
    block = srn.build_ablation_block(doc)
    assert block is not None
    # One row per stage the artefact holds, and a label for every stage: an unlabelled key
    # would be dropped from the table silently.
    for key in doc["stages"]:
        assert key in srn.ABLATION_LABELS, (
            f"stage {key!r} has no label, so it is missing from the generated table"
        )
        assert srn.ABLATION_LABELS[key] in block, key
    body = [ln for ln in block.splitlines() if ln.startswith("| ") and "---" not in ln]
    assert len(body) == len(doc["stages"]) + 1, (len(body), len(doc["stages"]))


def test_the_generated_table_states_the_nesting_verdict() -> None:
    """A stage that is not a superset makes every difference in the table ambiguous.

    The table reports differences between stages. If a stage dropped arms, a change could
    be arms added or arms lost and the reader cannot tell which, so the verdict belongs
    beside the numbers rather than in a separate section.
    """
    import json
    import pathlib
    import sys

    root = pathlib.Path(__file__).resolve().parents[1]
    artefact = root / "artifacts" / "corpus_ablation.json"
    if not artefact.exists():
        return
    sys.path.insert(0, str(root / "scripts"))
    import sync_report_numbers as srn

    doc = json.loads(artefact.read_text(encoding="utf-8"))
    block = srn.build_ablation_block(doc)
    dropped = sum(n.get("corpus_arms_dropped", 0) for n in doc.get("nesting") or [])
    assert f"**{dropped} corpus arms dropped**" in block
    assert dropped == 0, (
        f"{dropped} corpus arms are dropped across the stages, so the ablation is no "
        "longer interpretable as arms added"
    )


def test_every_processed_corpus_a_fit_reads_has_a_target_that_builds_it() -> None:
    """A directory no flag reproduces is a directory that drifts.

    `data/processed/with_explicit_threshold` was produced once by hand because
    `pmc-merge-explicit` omitted `--union`, and five hours later it held 22 agents while the
    corpus it is compared against held 34 -- so the censoring sensitivity refit would have
    charged twelve agents to the treatment. `corpus_ablation._frames` documents the same
    defect for the middle ablation stage, which is how it is known to recur. See negative
    result 54.

    The invariant is mechanical: every directory under `data/processed/` that holds an
    `arms.parquet` must be named as an output by some Makefile recipe.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    proc = root / "data" / "processed"
    if not proc.exists():
        return
    # The project's own variable for the processed root, as the recipes spell it.
    spellings = ("$(PROC)/", "data/processed/")
    missing = []
    for child in sorted(proc.rglob("arms.parquet")):
        child = child.parent
        if child == proc:
            continue
        # Deliberately retired corpora, with a README saying what they were and what
        # replaced them. Moved rather than deleted because no flag reproduces them.
        if "superseded" in child.parts:
            continue
        if any(f"{s}{child.name}" in makefile for s in spellings):
            continue
        missing.append(child.name)
    assert not missing, (
        "these processed corpora hold an arms.parquet and no Makefile recipe writes them, "
        f"so nothing keeps them in step with the corpus: {missing}. Add the target or "
        "delete the directory -- a fit that reads one cannot be interpreted."
    )
