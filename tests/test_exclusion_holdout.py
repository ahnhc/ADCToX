"""Tests for the non-circular exclusion-criteria holdout.

This is the plan's strongest claim about the comorbidity layer. A hand-assigned
condition-to-organ mapping cannot be validated against exclusion criteria because it was
written by reading them, leaving about 28 cells of FDA label text as the only non-circular
holdout. A MONDO `is_a` closure never saw the text, so the same test becomes legitimate
over 3,762 trials.

Two corrections are load-bearing and both are tested, because without either the result is
worthless rather than merely weaker.
"""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOLDOUT = ROOT / "artifacts" / "exclusion_holdout.json"

pytestmark = pytest.mark.skipif(
    not HOLDOUT.exists(), reason="run `make exclusion-holdout`"
)


def _load() -> dict:
    return json.loads(HOLDOUT.read_text(encoding="utf-8"))


def test_the_condition_matcher_groups_its_alternation() -> None:
    """A correctness bug that also made the whole evaluation irreproducible.

    The matcher was built as `(?<![a-z])alt1|alt2|alt3(?![a-z])`. `|` binds loosest, so the
    lookbehind applied to `alt1` only and the lookahead to `alt3` only, leaving every middle
    alternative with no word-boundary protection. Because the forms came out of a `set`,
    whichever alternative sorted first got the lookbehind -- and set iteration order varies
    with the per-process string hash seed, so two consecutive runs of the same command
    returned AUROC 0.674506 and 0.674111, with `active_autoimmune` matching 568 trials and
    then 642. Grouped and sorted deterministically it matches 558, below both, because the
    unprotected alternatives had been matching inside longer words.

    Found by chasing a 0.0004 difference between two runs of a reported number. A figure
    that moves between runs is worse than a wrong one, because it cannot be checked.
    """
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from exclusion_holdout import condition_matcher

    m = condition_matcher(
        "Active autoimmune disease", "autoimmune disease",
        {"autoimmune disorder", "autoimmune disease or disorder", "disease, autoimmune"},
    )
    assert m is not None
    assert m.pattern.startswith("(?<![a-z])(?:"), m.pattern
    assert m.pattern.endswith(")(?![a-z])"), m.pattern
    # Every alternative is inside the group, so none of them can match mid-word.
    assert not m.search("nonautoimmune disease")
    assert not m.search("autoimmune diseased")
    assert m.search("history of autoimmune disorder requiring")
    assert m.search("active autoimmune disease")

    # And the order is a pure function of the forms, not of set iteration.
    again = condition_matcher(
        "Active autoimmune disease", "autoimmune disease",
        {"disease, autoimmune", "autoimmune disease or disorder", "autoimmune disorder"},
    )
    assert again.pattern == m.pattern


def test_the_non_circular_mapping_beats_chance() -> None:
    """AUROC 0.666 with a permutation p of 0.0005. The permutation shuffles axis
    assignments *within* each condition, because the 11 cells of one condition are not
    independent -- their shares sum to one -- so a standard error over 293 cells would
    treat 27 conditions as 293."""
    d = _load()
    mondo = d["log2_share_enrichment"]["in_mondo"]
    assert mondo["auroc"] > 0.6, mondo["auroc"]
    assert mondo["permutation"]["p"] < 0.01, mondo["permutation"]
    # The null has to land on chance, or the permutation is not testing what it claims.
    assert 0.45 < mondo["permutation"]["null_mean"] < 0.55


def test_the_circular_mapping_scores_higher_and_that_is_the_point() -> None:
    """The hand map has circularity working for it, so it should win. The gap bounds what
    the circularity buys -- and a *smaller* gap is the interesting outcome, because it
    means the hand map is not living off the leak."""
    d = _load()
    mondo = d["log2_share_enrichment"]["in_mondo"]["auroc"]
    hand = d["log2_share_enrichment"]["in_hand"]["auroc"]
    assert hand > mondo, (hand, mondo)
    assert hand - mondo < 0.2, (
        "if the circular mapping pulls far ahead, the non-circular layer is not "
        "capturing what the hand map captures and the claim needs re-stating"
    )


def test_normalising_by_trial_share_is_what_removes_the_confound() -> None:
    """Any trial detailed enough to name a comorbidity sets thresholds on several organs,
    so raw rates come out enriched on every axis at once -- `ocular` was the top-enriched
    axis for both cirrhosis and chronic kidney disease. Shares sum to one within a trial,
    so protocol length cancels.

    The signature of the confound is both medians being positive. Under the raw metric they
    are; under shares the unassigned axes sit at zero, which is where they belong."""
    d = _load()
    raw = d["log2_enrichment"]["in_mondo"]
    share = d["log2_share_enrichment"]["in_mondo"]
    assert raw["median_negative"] > 0.3, (
        "the raw metric should show the confound: unassigned axes enriched too"
    )
    assert abs(share["median_negative"]) < 0.1, share["median_negative"]
    assert share["auroc"] > raw["auroc"]


def test_a_conditions_own_patterns_are_removed_before_flagging() -> None:
    """Without this the test is tautological. The organ-concern rules were also written by
    reading exclusion criteria and several *are* condition names: `cirrhosis` is a hepatic
    rule, `peripheral neuropath` a neurologic one, `inflammatory bowel|crohn` a
    gastrointestinal one, `hepatitis [bc]` and `hiv` infectious ones. For those conditions
    "mentions the condition" and "flags the organ" would be the same regex."""
    d = _load()
    removed = {
        p["condition"]: p["self_patterns_removed"]
        for p in d["pairs"] if p["self_patterns_removed"]
    }
    # At least the known self-matching conditions must have had something removed.
    for cid in ("cirrhosis", "peripheral_neuropathy", "inflammatory_bowel_disease"):
        if cid in d["conditions_tested"]:
            assert removed.get(cid), f"{cid} had no self-pattern removed"


def test_conditions_are_excluded_with_a_stated_reason() -> None:
    """14 of 41 are excluded and none silently. Six are pinned to the ontology root, so
    they derive no organ and cannot contribute a positive cell; the rest either have too
    few mentioning trials or a matcher that hit a quarter of the corpus, which means it was
    matching something generic."""
    d = _load()
    assert d["skipped"]
    for s in d["skipped"]:
        assert s["reason"] and len(s["reason"].split()) >= 3, s


def test_the_generic_matcher_guard_fires() -> None:
    """The defect it caught: six conditions pinned to the MONDO root were being matched
    with the root's own synonyms, so each hit about 60% of all trials and their enrichments
    came out identical to three decimals."""
    d = _load()
    hits = [s for s in d["skipped"] if "generic" in s["reason"]]
    # Either the guard fired, or every one of those conditions was already dropped for
    # having no derived axis -- both are correct outcomes, and a third is not.
    dropped = {s["id"] for s in d["skipped"]}
    assert hits or {"prior_anthracycline", "qt_prolongation"} <= dropped


def test_the_corpus_is_the_promised_size() -> None:
    """The whole argument for this layer is power: 3,762 trials against the 28 label cells
    that were the only other non-circular option."""
    d = _load()
    assert d["n_trials"] > 3000
    assert len(d["pairs"]) > 250
