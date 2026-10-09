"""The teammate-supplied database, and the two things that nearly went wrong ingesting it.

The first was a filter. "A row is usable if it has a numerator, a denominator and a
percentage" discarded 1,748 of 6,181 organ-specific any-grade rows -- 28% -- and among them
every one of the 883 regulatory-label rows, because a label table prints a percentage and a
denominator and no numerator. Usability and verifiability are different questions and the
first version asked only the second.

The second was counting. Their `Payload` field holds 33 distinct strings for 19 payloads:
five spellings of calicheamicin, seven of the tesirine/PBD/SG3199 family. Counting strings
would have inflated the payload vocabulary by 70% and manufactured a confirmation of
negative result 6, which is a claim about exactly that vocabulary's growth rate.

Skipped rather than failed where the workbook is absent: it is not redistributed, so a clean
clone does not have it.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "data" / "raw" / "atlas" / "2026-10-10" / "adc_db.xlsx"
INGEST = ROOT / "artifacts" / "atlas_ingest.json"
SCALE = ROOT / "artifacts" / "merged_corpus_scale.json"
DOMAINS = ROOT / "conf" / "ontology" / "atlas_domains.yaml"
SLOTS = ROOT / "conf" / "ontology" / "atlas_design_slots.yaml"


def _axes() -> set[str]:
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from adctox.taxonomy import Taxonomy
    return set(Taxonomy().axis_order)


def test_the_domain_crosswalk_targets_only_this_projects_axes() -> None:
    doc = yaml.safe_load(DOMAINS.read_text(encoding="utf-8"))
    unknown = set(doc["axis_of_domain"].values()) - _axes()
    assert not unknown, unknown


def test_every_dropped_domain_states_a_reason() -> None:
    """A domain that falls out of the corpus without a reason is invisible."""
    doc = yaml.safe_load(DOMAINS.read_text(encoding="utf-8"))
    for label, entry in (doc.get("dropped") or {}).items():
        assert entry.get("reason", "").strip(), label
        assert isinstance(entry.get("rows"), int), label


def test_the_crosswalk_covers_every_axis() -> None:
    """Not a requirement in principle, but true here, and a regression if it stops being.

    If a future edit leaves an axis with no source domain, that axis silently gets no cells
    from this corpus -- which is what happened to otologic for a different reason, and was
    only noticed by counting.
    """
    doc = yaml.safe_load(DOMAINS.read_text(encoding="utf-8"))
    assert set(doc["axis_of_domain"].values()) == _axes()


def test_payload_strings_collapse_and_every_identity_has_a_mechanism() -> None:
    doc = yaml.safe_load(SLOTS.read_text(encoding="utf-8"))
    strings = doc["payload_identity"]
    identities = set(strings.values())
    assert len(strings) > len(identities), (
        "the normalisation table no longer collapses anything, so either the source "
        "stopped using alternative spellings or the table lost its entries"
    )
    assert not identities - set(doc["mechanism_of_payload"]), (
        identities - set(doc["mechanism_of_payload"])
    )
    assert not identities - set(doc["family_of_payload"]), (
        identities - set(doc["family_of_payload"])
    )


def test_only_one_linker_label_is_non_cleavable() -> None:
    """Their fourteen linker strings name a cleavage route or say "Non-cleavable".

    If a second non-cleavable label appears, the binary is no longer a lookup and the
    mapping needs a human, not a default.
    """
    doc = yaml.safe_load(SLOTS.read_text(encoding="utf-8"))
    non = [k for k, v in doc["cleavable_of_linker_type"].items() if not v]
    assert non == ["Non-cleavable"], non


def test_a_post_freeze_mechanism_addition_carries_a_date_and_a_reason() -> None:
    """The mechanism taxonomy is frozen; its own rule is that additions are recorded."""
    doc = yaml.safe_load(SLOTS.read_text(encoding="utf-8"))
    for name, entry in (doc.get("post_freeze_additions") or {}).items():
        assert entry.get("added"), name
        assert entry.get("justification", "").strip(), name
        # A single-agent level cannot be a held-out fold, and saying so is what separates a
        # genuine new mechanism from taxonomy inflation.
        assert "holdout_viable" in entry, name


@pytest.mark.skipif(not INGEST.exists(), reason="run `make atlas-ingest`")
def test_label_rows_survive_the_gate() -> None:
    """The regression that matters: percentage-and-denominator rows must be kept.

    883 of them exist, all from regulatory labels, and the first version of the filter
    dropped every one.
    """
    doc = json.loads(INGEST.read_text(encoding="utf-8"))
    assert doc["source_tiers"].get("label", 0) > 0, (
        "no label-derived arms survived ingestion; the usability filter is requiring a "
        "numerator that label tables do not print"
    )
    assert doc["arithmetic_gate"]["numerator_reconstructed_from_percentage"] > 0


@pytest.mark.skipif(not INGEST.exists(), reason="run `make atlas-ingest`")
def test_a_reconstructed_numerator_is_not_counted_as_verified() -> None:
    """Checking a derived numerator against the percentage it came from is circular."""
    doc = json.loads(INGEST.read_text(encoding="utf-8"))
    gate = doc["arithmetic_gate"]
    assert gate["verifiable"] + gate["not_verifiable"] > 0
    assert gate["numerator_reconstructed_from_percentage"] <= gate["not_verifiable"], (
        "reconstructed numerators are being counted among the verifiable rows, which makes "
        "the pass rate pass by construction"
    )


@pytest.mark.skipif(not INGEST.exists(), reason="run `make atlas-ingest`")
def test_the_source_tier_has_more_than_two_levels() -> None:
    """The reason the field exists. Negative result 34 measured the reporting-source gap at
    up to 1.85 logit on one axis, larger than the mechanism effect, so four document kinds
    cannot be absorbed by a registry/literature binary."""
    doc = json.loads(INGEST.read_text(encoding="utf-8"))
    assert len(doc["source_tiers"]) >= 3, doc["source_tiers"]


@pytest.mark.skipif(not INGEST.exists(), reason="run `make atlas-ingest`")
def test_the_funnel_only_ever_loses_rows() -> None:
    doc = json.loads(INGEST.read_text(encoding="utf-8"))
    rows = [f["rows"] for f in doc["funnel"]]
    assert rows == sorted(rows, reverse=True), doc["funnel"]


MERGE = ROOT / "artifacts" / "atlas_merge.json"


@pytest.mark.skipif(not SCALE.exists(), reason="run `make merged-scale`")
def test_the_merged_corpus_is_a_superset_of_both() -> None:
    doc = json.loads(SCALE.read_text(encoding="utf-8"))
    by = {r["corpus"]: r for r in doc["corpora"]}
    merged = by["merged"]
    for name in ("registry + literature (ours)", "atlas only"):
        assert merged["agents"] >= by[name]["agents"], name
        assert merged["identifying_cells_observed"] >= by[name]["identifying_cells_observed"]
        assert merged["payload_identities"] >= by[name]["payload_identities"], name


@pytest.mark.skipif(not SCALE.exists(), reason="run `make merged-scale`")
def test_the_two_definitions_of_identifying_cells_are_kept_apart() -> None:
    """The defect that reported a met floor as unmet.

    `capacity` is agents x axes, which is what the model's parameter accounting counts and
    what the plan's 8:1 floor was written against. `observed` counts only the agent-axis
    pairs carrying data. The first version of this measurement reported the second against
    the first's threshold, understating the merged corpus by a third. Both are now present,
    the floor verdict is taken from capacity, and observed can never exceed it.
    """
    doc = json.loads(SCALE.read_text(encoding="utf-8"))
    for r in doc["corpora"]:
        cap, obs = r["identifying_cells_capacity"], r["identifying_cells_observed"]
        if cap is None:
            continue
        assert obs <= cap, r
        assert r["ratio_capacity"] == pytest.approx(cap / doc["design_parameters"], abs=0.01)
        assert r["meets_identification_floor"] == (
            r["ratio_capacity"] >= doc["identification_floor"]
        ), r


@pytest.mark.skipif(not SCALE.exists(), reason="run `make merged-scale`")
def test_the_granularity_ladder_is_ordered_and_uses_the_plans_ratio() -> None:
    """Coarser levels must have fewer parameters and therefore a higher ratio.

    The ladder is what the plan used to choose the mechanism level and to rule the family
    level out. Re-running it rather than re-asserting it is the point: at the merged corpus
    size the family level reaches the floor the plan said it never would.
    """
    doc = json.loads(SCALE.read_text(encoding="utf-8"))
    ladder = doc.get("granularity_ladder") or []
    if not ladder:
        return
    by_level = {L["level"]: L for L in ladder}
    assert {"mechanism", "payload_family", "payload_identity"} <= set(by_level)
    ratios = [by_level[k]["ratio"] for k in
              ("mechanism", "payload_family", "payload_identity")]
    assert ratios == sorted(ratios, reverse=True), ladder
    for L in ladder:
        assert L["parameters"] == (L["levels"] - 1) * 14, L
        assert L["meets_identification_floor"] == (L["ratio"] >= doc["identification_floor"])


@pytest.mark.skipif(not SCALE.exists(), reason="run `make merged-scale`")
def test_payload_identity_stays_below_the_floor() -> None:
    """Negative result 6, as an invariant rather than a sentence.

    If payload identity ever clears the floor, the report's most load-bearing structural
    claim has changed and must be re-derived rather than kept.
    """
    doc = json.loads(SCALE.read_text(encoding="utf-8"))
    ladder = {L["level"]: L for L in (doc.get("granularity_ladder") or [])}
    if "payload_identity" not in ladder:
        return
    assert not ladder["payload_identity"]["meets_identification_floor"], (
        f"payload identity reached {ladder['payload_identity']['ratio']}:1. Result 6 says "
        "this cannot happen at any reachable corpus size; re-derive it."
    )


@pytest.mark.skipif(not SCALE.exists(), reason="run `make merged-scale`")
def test_the_payload_vocabulary_growth_rate_is_reported_per_corpus() -> None:
    doc = json.loads(SCALE.read_text(encoding="utf-8"))
    for r in doc["corpora"]:
        assert r["payloads_per_agent"] > 0
        assert r["payloads_per_agent"] == pytest.approx(
            r["payload_identities"] / r["agents"], abs=0.002)


@pytest.mark.skipif(not MERGE.exists(), reason="run `make atlas-merge`")
def test_the_merge_refuses_cohorts_whose_patients_are_already_counted() -> None:
    """Ten atlas cohorts name a trial the base corpus already holds for the same agent.

    Keeping them would inflate the denominator with the same patients twice, which is worse
    than losing an arm: a false denominator moves every rate on that arm.
    """
    doc = json.loads(MERGE.read_text(encoding="utf-8"))
    assert doc["dropped_as_already_counted"] > 0, (
        "no cohort was dropped as already counted. Either the base corpus changed or the "
        "(agent, NCT) check stopped matching -- verify before trusting the merged totals."
    )
    merged, base, added = doc["merged"], doc["base"], doc["atlas_added"]
    assert merged["arms"] == base["arms"] + added["arms"]
    assert merged["agents"] <= base["agents"] + added["agents"]


@pytest.mark.skipif(not MERGE.exists(), reason="run `make atlas-merge`")
def test_the_residual_overlap_exposure_is_measured_and_not_assumed_zero() -> None:
    """86 atlas cohorts name no NCT, so the check cannot run on them.

    The exposure is only real where the base corpus already has arms for that agent; for a
    new agent there is nothing to collide with. That bound is the honest number and it is
    recorded rather than left as "we deduplicated".
    """
    doc = json.loads(MERGE.read_text(encoding="utf-8"))
    exp = doc["overlap_exposure"]
    assert exp["arms_without_nct"] >= exp["residual_overlap_exposure_arms"]
    assert len(exp["residual_overlap_exposure_agents"]) > 0, (
        "the exposure is reported as zero; if that is now true the note should say why "
        "rather than the field reading as a default"
    )


@pytest.mark.skipif(not MERGE.exists(), reason="run `make atlas-merge`")
def test_the_merged_corpus_carries_more_than_two_source_tiers() -> None:
    doc = json.loads(MERGE.read_text(encoding="utf-8"))
    tiers = doc["source_tiers"]
    assert "registry" in tiers and tiers["registry"] > 0, (
        f"no registry arms in the merged corpus: {tiers}. An earlier version keyed the tier "
        'on source == "ctgov", which no row carries, and labelled all 2,201 registry arms '
        "as publications."
    )
    assert len(tiers) >= 4, tiers


AUDIT = ROOT / "artifacts" / "precedent_audit.json"


@pytest.mark.skipif(not AUDIT.exists(), reason="run `make precedent-audit`")
def test_the_precedent_audit_keeps_the_two_directions_apart() -> None:
    """Below what can be named is an error; above it is unverified.

    Conflating them would report nine wrong counts where there are four. The count is used
    as a floor -- C4 refuses a design when it is zero and O3 ranks on it -- so an undercount
    changes behaviour and an overcount only fails to be confirmable from this corpus.
    """
    doc = json.loads(AUDIT.read_text(encoding="utf-8"))
    for r in doc["payloads"]:
        assert r["curated_below_named"] == (r["curated"] < r["named_union"]), r
        # The union can never be smaller than either source it is built from.
        assert r["named_union"] >= r["named_in_corpus"], r
        assert r["named_union"] >= r["named_in_workbook"], r
        assert r["named_union"] <= r["named_in_corpus"] + r["named_in_workbook"], r
    under = [r for r in doc["payloads"] if r["curated_below_named"]]
    assert doc["summary"]["n_curated_below_named"] == len(under)


@pytest.mark.skipif(not AUDIT.exists(), reason="run `make precedent-audit`")
def test_absent_payloads_are_reported_with_what_blocks_them() -> None:
    """A payload the corpus names and the design space lacks cannot be proposed.

    Listing it without saying what adding it needs would read as a configuration oversight.
    It is not: constraint C1 needs a free-payload IC50 and C5 needs an attachment group,
    and neither source carries either.
    """
    doc = json.loads(AUDIT.read_text(encoding="utf-8"))
    absent = doc["payloads_absent_from_design_space"]
    assert doc["summary"]["n_payloads_absent_from_design_space"] == len(absent)
    if absent:
        assert doc["summary"]["blocked_on"].strip()
        for a in absent:
            assert a["named_union"] == len(a["agents"]) >= 1, a


@pytest.mark.skipif(not AUDIT.exists(), reason="run `make precedent-audit`")
def test_the_audit_records_that_the_counts_were_hand_curated() -> None:
    """The provenance is the reason the audit exists, so it is carried, not assumed."""
    doc = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert doc["counts_source"] == "hand_curated_landscape_review"
    assert doc["design_space_frozen_at"]


SCALES = ROOT / "artifacts" / "posterior_scales.json"
EVIDENCE = ROOT / "artifacts" / "axis_evidence.json"


@pytest.mark.skipif(not SCALES.exists(), reason="run `make posterior-scales`")
def test_a_zero_width_interval_is_flagged_as_a_frozen_sampler() -> None:
    """How the DAR parse error of result 47 presented itself.

    A posterior interval of width zero on 400 draws is not precision, it is a chain that
    never moved. Flagging it in the artefact is what turns the next occurrence into a line
    of output rather than a misdiagnosis.
    """
    doc = json.loads(SCALES.read_text(encoding="utf-8"))
    for r in doc["corpora"]:
        for name, v in r["scales"].items():
            assert v["degenerate"] == (v["width"] < 1e-6), (r["corpus"], name)
            assert v["q05"] <= v["mean"] <= v["q95"], (r["corpus"], name)
    assert doc["summary"]["degenerate_parameters"] == [
        f"{r['corpus']}/{k}" for r in doc["corpora"]
        for k, v in r["scales"].items() if v["degenerate"]
    ]


@pytest.mark.skipif(not SCALES.exists(), reason="run `make posterior-scales`")
def test_a_corpus_with_one_source_is_not_reported_as_wholly_confounded() -> None:
    """Two situations look alike in a share and are opposite in consequence.

    No source variation at all means the source term is not sampled and `sigma_agent` means
    what its name says. Variation that some agents do not span means the term is estimated
    *and* those agents absorb it. Reporting the first as "100% single-source" would read as
    the worst case when it is the clean one.
    """
    doc = json.loads(SCALES.read_text(encoding="utf-8"))
    for r in doc["corpora"]:
        ident = r["identifiability"]
        assert "source_term_sampled" in ident, r["corpus"]
        if not ident["source_term_sampled"]:
            assert ident["single_source_share"] is None, r["corpus"]
            assert ident["both_sources"] == 0
        else:
            assert ident["both_sources"] + ident["single_source"] == ident["agents"]
            assert ident["single_source_share"] == pytest.approx(
                ident["single_source"] / ident["agents"], abs=1e-4)


@pytest.mark.skipif(not SCALES.exists(), reason="run `make posterior-scales`")
def test_the_identifiability_share_is_counted_on_the_arms_the_grid_keeps() -> None:
    """Three plausible denominators give 62%, 64% and 67%, and only one is the fit's view.

    The builder drops arms with no observation and below the denominator floor, so an agent
    whose only registry arm was dropped is literature-only as far as the fit is concerned.
    Counting over parquet rows, or over every arm of a surviving agent, disagrees with the
    separability audit -- which is the same two-quantities-one-name defect as results 38
    and 44, in a third place.
    """
    doc = json.loads(SCALES.read_text(encoding="utf-8"))
    audit = ROOT / "artifacts" / "source_confounding_atlas.json"
    merged = next((r for r in doc["corpora"] if r["corpus"] == "merged"), None)
    if merged is None or not audit.exists():
        return
    agent_level = json.loads(audit.read_text(encoding="utf-8"))["summary"]["agent_level"]
    assert merged["identifiability"]["both_sources"] == agent_level["n_both_sources"], (
        "posterior_scales.py and source_confounding_audit.py disagree about how many "
        "agents span both sources; they must count the same thing"
    )
    assert merged["identifiability"]["agents"] == agent_level["n_agents"]


@pytest.mark.skipif(not EVIDENCE.exists(), reason="run `make axis-evidence`")
def test_a_stalled_axis_is_reported_as_stalled() -> None:
    """Otologic gains nothing from 46 new agents, and that is a finding rather than a gap."""
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    for r in doc["growth"]:
        assert r["stalled"] == (r["agents_last"] == r["agents_first"]), r
        assert r["agents_gained"] == r["agents_last"] - r["agents_first"], r
        assert r["agents_gained"] >= 0, (
            f"{r['axis']} lost agents as the corpus grew, which cannot happen if each "
            "stage is a superset of the last"
        )
    assert doc["summary"]["stalled_axes"] == [
        r["axis"] for r in doc["growth"] if r["stalled"]
    ]


@pytest.mark.skipif(not EVIDENCE.exists(), reason="run `make axis-evidence`")
def test_the_thin_flag_is_checked_against_the_interval_it_sits_beside() -> None:
    """A warning that repeats the interval is decoration; one that does not is information.

    The thin flag's threshold is borrowed from `min_agents_for_holdout`, and borrowing a
    threshold from a different question is the defect this session kept finding. So the
    check is whether the credible interval already encodes the agent count. It does not --
    weak rank correlation, non-monotone medians -- which is what makes the flag carry
    something and what rules out justifying its threshold as a precision cut-off.
    """
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    tvi = doc.get("thinness_vs_interval")
    if not tvi:
        return
    rho = tvi["spearman_agents_vs_relative_interval_width"]
    assert -1.0 <= rho <= 1.0
    # More agents should not make the interval *wider* on average; a positive correlation
    # would mean the evidence count and the uncertainty point opposite ways and the flag
    # would need rethinking rather than defending.
    assert rho <= 0.0, (
        f"supporting agents correlate positively with interval width at {rho:+.4f}; the "
        "thin flag and the interval would then be telling opposite stories"
    )
    # And if it ever becomes strong and monotone, the flag IS the interval and should go.
    if tvi["monotone"] and rho < -0.8:
        raise AssertionError(
            f"the interval now encodes the agent count (rho {rho:+.4f}, monotone), so the "
            "thin flag is telling the reader the same thing twice and should be removed "
            "rather than kept out of habit"
        )
    counts = tvi["by_supporting_agents"]
    assert sum(v["cells"] for v in counts.values()) == tvi["cells"]


CONV = ROOT / "artifacts" / "convergence_conditions.json"


@pytest.mark.skipif(not CONV.exists(), reason="run `make convergence-conditions`")
def test_the_prediction_is_recorded_before_its_outcome() -> None:
    """A prediction kept beside its result is the only kind that can be wrong usefully.

    One was written down before the merged corpus was fitted -- that it would fail its
    seed-agreement check, because the 32-agent fit failed and the merged corpus has worse
    upper-bound reporting cuts. The artefact carries the claim, the reasoning and the
    outcome, so the refutation is as legible as a confirmation would have been.
    """
    doc = json.loads(CONV.read_text(encoding="utf-8"))
    pred = doc["prediction"]
    assert pred["made"].strip() and pred["because"].strip()
    assert pred["outcome"] in (None, "confirmed", "refuted")
    merged = next((r for r in doc["fits"] if r["fit"] == "65 agents, default"), None)
    if merged and merged["status"] == "fitted":
        assert pred["outcome"] == ("refuted" if merged["converged"] else "confirmed")
    else:
        assert pred["outcome"] is None, (
            "an outcome is recorded for a fit that has not landed"
        )


@pytest.mark.skipif(not CONV.exists(), reason="run `make convergence-conditions`")
def test_the_second_prediction_is_also_recorded_before_its_outcome() -> None:
    """Chain steps 3 and 4 reach the same censoring state by two routes.

    Dropping uninformative absences from the 32-agent corpus leaves 663 censored cells;
    keeping only the tables that stated a cut leaves 663 on 26 agents. So the pair separates
    "the damage is the bounded threshold" from "the damage is the literature arms", and the
    prediction -- that the explicit-cuts fit lands nearer the registry corpus -- is written
    down before the fit so the refutation would be as legible as the confirmation.
    """
    doc = json.loads(CONV.read_text(encoding="utf-8"))
    pred = doc["prediction_two"]
    assert pred["made"].strip() and pred["because"].strip()
    assert pred["outcome"] in (None, "confirmed", "refuted")
    explicit = next((r for r in doc["fits"] if r["fit"] == "explicit cuts only"), None)
    if explicit and explicit["status"] == "fitted" and explicit.get("lomo_delta") is not None:
        # Scored only against fits that have landed, and by the stated rule.
        reg = next((r.get("lomo_delta") for r in doc["fits"]
                    if r["fit"] == "registry, default"), None)
        exp = next((r.get("lomo_delta") for r in doc["fits"]
                    if r["fit"] == "32 agents, absences dropped"), None)
        if reg is not None and exp is not None:
            want = "confirmed" if abs(explicit["lomo_delta"] - reg) < abs(
                explicit["lomo_delta"] - exp) else "refuted"
            assert pred["outcome"] == want
    else:
        assert pred["outcome"] is None, (
            "an outcome is recorded for the explicit-cuts fit, which has not landed"
        )


@pytest.mark.skipif(not CONV.exists(), reason="run `make convergence-conditions`")
def test_no_fit_is_summarised_before_it_has_run() -> None:
    """The table shortens rather than guessing: a fit with no artefact gets no row of
    numbers, because a blank and a zero are different and only one of them is true."""
    doc = json.loads(CONV.read_text(encoding="utf-8"))
    for r in doc["fits"]:
        if r["status"] == "fitted":
            assert r["cells"] and r["agents"], r
            continue
        assert "worst_seed_gap" not in r and "cells" not in r, r
    fitted = [r for r in doc["fits"] if r["status"] == "fitted"]
    assert doc["summary"]["n_fitted"] == len(
        [r for r in fitted if r["converged"] is not None]
    )


@pytest.mark.skipif(not CONV.exists(), reason="run `make convergence-conditions`")
def test_the_convergence_verdict_follows_the_gap_and_the_threshold() -> None:
    doc = json.loads(CONV.read_text(encoding="utf-8"))
    for r in doc["fits"]:
        if r["status"] != "fitted" or r["worst_seed_gap"] is None:
            continue
        assert r["converged"] == (r["worst_seed_gap"] <= r["seed_threshold"]), r
        if r["censored_share"] is not None:
            assert 0.0 <= r["censored_share"] <= 1.0, r


COMPAR = ROOT / "artifacts" / "fold_comparability.json"


@pytest.mark.skipif(not COMPAR.exists(), reason="run `make fold-comparability`")
def test_the_like_for_like_macro_uses_folds_every_corpus_has() -> None:
    """A corpus must not be penalised for having gained a fourth and harder fold.

    The merged corpus has `dna_cleave` and the registry corpus does not, so comparing a
    four-fold macro against a three-fold one would charge the merged corpus for a test the
    others never took. The like-for-like macro is over the intersection.
    """
    doc = json.loads(COMPAR.read_text(encoding="utf-8"))
    common = set(doc["common_folds"])
    if not common:
        return
    for corpus, v in doc["like_for_like_macro"].items():
        assert set(v["folds"]) == common, corpus
        deltas = [r["delta_auc"] for r in doc["rows"]
                  if r["corpus"] == corpus and r["fold"] in common]
        assert v["macro_delta"] == pytest.approx(sum(deltas) / len(deltas), abs=1e-4)
    # Every corpus present must carry every common fold, or the intersection is wrong.
    for corpus in {r["corpus"] for r in doc["rows"]}:
        got = {r["fold"] for r in doc["rows"] if r["corpus"] == corpus}
        assert common <= got, (corpus, sorted(common - got))


@pytest.mark.skipif(not COMPAR.exists(), reason="run `make fold-comparability`")
def test_the_share_held_out_is_measured_rather_than_assumed_irrelevant() -> None:
    """The confound, quantified instead of waved away.

    A fold that removes more of the corpus is a harder test, and the expansions are
    tubulin-heavy, so tubulin removes 45%, 50% and 63% in turn. If the degradation tracked
    that, part of the headline would be the expansion's composition rather than its quality.
    Measured, the correlation is weak -- which is what licenses reading the degradation as
    being about content.
    """
    doc = json.loads(COMPAR.read_text(encoding="utf-8"))
    for r in doc["rows"]:
        if r["agent_share_held_out"] is None:
            continue
        assert 0.0 < r["agent_share_held_out"] <= 1.0, r
        assert 0.0 < r["cell_share_held_out"] <= 1.0, r
    rho = doc["summary"]["spearman_delta_vs_agent_share_held_out"]
    if rho is None:
        return
    assert -1.0 <= rho <= 1.0
    # If it ever becomes strong, the cross-corpus comparison needs restating rather than
    # repeating: the folds would no longer be measuring the same thing.
    assert abs(rho) < 0.7, (
        f"the delta now tracks the share held out at {rho:+.4f}, so part of the "
        "cross-corpus degradation is fold size and the comparison must say so"
    )


@pytest.mark.skipif(not EVIDENCE.exists(), reason="run `make axis-evidence`")
def test_a_thin_axis_is_checked_against_whether_it_reaches_the_output() -> None:
    """Thin evidence only matters where it surfaces.

    Otologic rests on 28% of the corpus's agents. If it never reaches a candidate's top
    three, the thinness is real and not load-bearing; if it does, the product is ranking on
    its weakest evidence. The two questions are asked in one pass, and the answer to the
    second is the finding: four of fourteen axes ever place. See negative results 49 and 56.
    """
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    out = doc.get("axes_reaching_the_output")
    if not out:
        return
    reaching = set(out["axes_reaching_top_three"])
    never = set(out["axes_never_reaching_top_three"])
    assert reaching & never == set()
    assert len(reaching) + len(never) == doc["summary"]["n_axes"]
    assert out["n_axes_reaching_top_three"] == len(reaching)
    # Every axis in a top-three count must be one of the axes said to reach it.
    assert set(out["top_three_counts"]) == reaching
    assert set(out["worst_axis_counts"]) <= reaching
    # No count may exceed the candidates, and the top-three counts must sum to three per
    # candidate -- otherwise the ranking is being read wrong.
    assert sum(out["top_three_counts"].values()) == 3 * out["candidates"]
    assert sum(out["worst_axis_counts"].values()) == out["candidates"]
    thin = {r["axis"] for r in doc["growth"] if r["thin"]}
    if thin & reaching:
        raise AssertionError(
            f"thin axes {sorted(thin & reaching)} now reach a candidate's top three, so "
            "the product is ranking on its weakest evidence and result 56's reassuring "
            "half no longer holds"
        )
