"""One clinical event must not land on three different axes by sponsor coding.

"Infusion related reaction" appears 408 times in the registry: 192 rows filed under
`immune system disorders`, which map to infectious_immune; 31 under `general disorders`,
which map to constitutional; and 178 under `injury, poisoning and procedural complications`,
which are dropped entirely. So whether an infusion reaction is counted at all, and on which
axis, was decided by the sponsor's coding rather than by the event -- 1,725 patients' worth
of a named ADC toxicity discarded, and the remainder split in two.

MedDRA's primary SOC for the term *is* injury/poisoning/procedural, which is why it lands
there. The exclusion of that SOC was aimed at procedural harm -- 234 rows of falls, 104 of
contusions, femur fractures -- and this is a drug reaction that shares their SOC.

The rule is a term-level override applied before the SOC lookup, by exact normalized term
rather than by pattern, so an entry can only affect the event it names. The discipline the
rest of the taxonomy follows -- "the SOC gates the term", which stops "Blood creatinine
increased" being stolen by a renal pattern when it is filed under a real SOC -- is preserved
because nothing here is a pattern.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXCLUDED_SOC = "injury, poisoning and procedural complications"


def test_the_same_term_gets_the_same_axis_whatever_soc_it_arrives_under() -> None:
    tax = default_taxonomy()
    axes = {
        tax.resolve("Infusion related reaction", soc)[0]
        for soc in (
            "immune system disorders",
            "general disorders",
            "general disorders and administration site conditions",
            EXCLUDED_SOC,
            None,
        )
    }
    assert axes == {"infectious_immune"}, axes


def test_the_rescue_does_not_reopen_the_exclusion() -> None:
    """The SOC is excluded for procedural harm and stays excluded for it."""
    tax = default_taxonomy()
    for term in ("Fall", "Contusion", "Femur fracture", "Head injury",
                 "Allergic transfusion reaction"):
        axis, prov = tax.resolve(term, EXCLUDED_SOC)
        assert axis == "__excluded__", (term, axis, prov)


def test_the_soc_still_gates_every_pattern() -> None:
    """The reason the override is an exact term and not a pattern. An `Investigations` rule
    may only fire on a term whose SOC is `Investigations`, or "Blood creatinine increased"
    filed under a real SOC would be stolen by the renal pattern."""
    tax = default_taxonomy()
    assert tax.resolve("Blood creatinine increased", "Investigations")[0] == "renal"
    axis, _ = tax.resolve("Blood creatinine increased", "Renal and urinary disorders")
    assert axis == "renal"
    # And a term the override does not name is untouched by it.
    axis, prov = tax.resolve("Hypersensitivity", "Immune system disorders")
    assert axis == "infectious_immune"
    assert "term_axis" not in prov


def test_every_override_names_a_real_axis_and_says_why() -> None:
    """A typo in the axis would make the entry silently unreachable, and an entry without a
    reason is a judgement nobody can check."""
    doc = yaml.safe_load(
        (ROOT / "conf" / "ontology" / "axes.yaml").read_text(encoding="utf-8")
    )
    overrides = doc.get("term_axis") or {}
    assert overrides, "the override table is empty"
    for term, axis in overrides.items():
        assert axis in doc["axes"], (term, axis)
    # The reason lives in the comment block above the table, which has to mention the
    # count that justifies it.
    text = (ROOT / "conf" / "ontology" / "axes.yaml").read_text(encoding="utf-8")
    head = text[: text.index("term_axis:")]
    assert "408" in head and "178" in head, "the override's justification is not stated"


@pytest.mark.skipif(
    not (ROOT / "data" / "processed" / "arms.parquet").exists(),
    reason="run `make corpus`",
)
def test_the_rescued_rows_reach_the_corpus() -> None:
    """The point of the rule. Before it, no registry arm carried an infusion reaction from
    the excluded SOC at all."""
    import json

    report = ROOT / "data" / "processed" / "taxonomy_report.json"
    if not report.exists():
        pytest.skip("run `make taxonomy`")
    doc = json.loads(report.read_text(encoding="utf-8"))
    rows = doc["rows_by_axis"]
    # The exclusion shrinks and the immune axis grows; both have to move, or the rule did
    # nothing and this test is checking a number that was already there.
    assert rows.get("__excluded__", 0) < 6249, rows.get("__excluded__")
    assert rows.get("infectious_immune", 0) > 10893, rows.get("infectious_immune")
