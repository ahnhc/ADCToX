"""Tests for the FDA label impairment evaluation.

The plan designated this as the single validation to build for the comorbidity layer. The
measurement says it is misspecified, and the tests pin the diagnosis rather than the null,
because a null reported without its diagnosis would read as the model failing.
"""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "artifacts" / "label_impairment_eval.json"

pytestmark = pytest.mark.skipif(
    not EVAL.exists(), reason="run `make label-impairment`"
)


def _load() -> dict:
    return json.loads(EVAL.read_text(encoding="utf-8"))


def test_the_impairment_sections_argue_from_clearance_not_organ_events() -> None:
    """The finding that reframes the whole test. A label's impairment guidance says what
    happens to *exposure* when an organ is compromised -- ADCETRIS: "MMAE exposure and
    adverse reactions are increased"; inotuzumab ozogamicin: "based on a population
    pharmacokinetic analysis, the clearance ..." -- while the model predicts organ-specific
    event rates.

    Pharmacokinetic language outnumbers organ-event language roughly six to one, and the
    ratio is stable whether the text window is the subsection alone (6 cells to 1) or 900
    characters around the phrase (10 to 2). The ratio is the robust statement; the
    individual shares move with the window."""
    w = _load()["what_the_sections_argue_from"]
    assert w["mentions_pharmacokinetics"] >= 3 * max(1, w["mentions_organ_event"]), w
    assert w["note"]


def test_the_ordinal_correlation_is_null_and_that_is_the_expected_answer() -> None:
    """Comparing a clearance-driven use restriction against an organ event rate should not
    correlate. Asserting the null keeps a future change honest: if this ever becomes
    significant, something about the comparison changed and needs explaining, not
    celebrating."""
    d = _load()
    for key in ("all_levels", "without_not_established"):
        block = d[key]
        if block.get("spearman") is None:
            continue
        assert abs(block["spearman"]) < 0.5, (key, block)
        assert block["p"] > 0.05, (key, block)


def test_the_cross_organ_statements_are_found() -> None:
    """What the labels do support, and the plan's G3 test. Three sentences, all of the form
    "impairment in one organ raises events in another" -- and all three are renal, which is
    consistent with the clearance mechanism rather than with tissue overlap."""
    d = _load()
    assert len(d["cross_organ_sentences"]) >= 2
    agents = {x["agent"] for x in d["cross_organ_sentences"]}
    assert "trastuzumab_deruxtecan" in agents, agents
    joined = " ".join(x["sentence"] for x in d["cross_organ_sentences"]).lower()
    assert "renal" in joined
    # The T-DXd sentence is the one the plan quotes: renal impairment raising ILD.
    assert any(
        "ild" in x["sentence"].lower() or "pneumonitis" in x["sentence"].lower()
        for x in d["cross_organ_sentences"]
    )


def test_missing_cells_are_genuine_label_silence_not_parser_failure() -> None:
    """A parser dropping cells and a label saying nothing look identical in the output, and
    the first version of this script conflated them: a lookahead on a newline that had
    already been normalised away reported nine of fourteen renal sections as absent. The
    plan's measured figure -- renal text in 13 of 14 labels -- is what exposed it.

    After the fix, nine of ten missing cells have no section at all, which is the label
    being silent. `sacituzumab_govitecan` and `polatuzumab_vedotin` mention renal zero
    times anywhere in Use in Specific Populations."""
    d = _load()
    missing = d["missing"]
    truly_absent = [m for m in missing if not m["section_present"]]
    assert len(truly_absent) >= 0.7 * len(missing), (
        "most missing cells should be label silence; if the section is present and "
        "ungraded, the guidance vocabulary needs extending"
    )


def test_every_graded_cell_carries_the_sentence_it_was_graded_from() -> None:
    """An ordinal level with no quotation behind it is an assertion."""
    d = _load()
    assert d["cells"]
    for c in d["cells"]:
        assert c["evidence"] and len(c["evidence"].split()) >= 4, c
        assert c["level"] in d["levels"]
