"""The sentence beside `sigma_agent` has to follow the number, not outlive it.

The generator printed "small, so the design slots account for much of the between-agent
variation" beside whatever value the fit produced. That reading was written when the
parameter stood at 0.159 on the 16-agent registry corpus. The corpus rebuild moved it to
0.343 -- 0.63 times `tau_mech`, which is what it was being called small against -- and the
sentence did not move, because `check_report.py` pins every decimal figure to an artefact
and has no power at all over the prose beside it.

So the reading is now selected by the ratio and these tests hold it to that: the bands are
ordered, the note changes when the ratio crosses one, and the note names the ratio it read.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import residual_scale as rs  # noqa: E402
import sync_report_numbers as srn  # noqa: E402


def _metrics(sigma: float, tau: float) -> dict:
    return {
        "tau_mech": {"mean": tau, "q05": tau * 0.8, "q95": tau * 1.2},
        "coefficients": {
            "sigma_agent": {"mean": sigma, "q05": sigma * 0.7, "q95": sigma * 1.4}
        },
    }


def test_the_bands_are_ordered() -> None:
    assert 0.0 < rs.ACCOUNTS_FOR < rs.DOES_NOT_ACCOUNT_FOR


def test_the_reading_follows_the_ratio() -> None:
    """Three ratios, three different readings. The old sentence was one reading for all."""
    low = rs._ratio(_metrics(0.10, 1.00))["reading"]
    mid = rs._ratio(_metrics(0.60, 1.00))["reading"]
    high = rs._ratio(_metrics(1.50, 1.00))["reading"]
    assert low != mid != high and low != high
    assert "account for much" in low
    assert "do not account" in high


def test_the_note_the_report_prints_names_the_ratio_it_read() -> None:
    """A sentence that quotes its own input cannot drift from it silently.

    The failure this prevents is exactly the original one: prose that reads as a conclusion
    while being a constant. If the number it quotes is in the sentence, `check_report.py`
    regains power over the claim, because the claim now contains a figure.
    """
    note = srn._sigma_agent_note(_metrics(0.3433, 0.5424))
    assert note is not None
    assert "0.6329" in note, note
    assert "0.5424" in note, note


def test_the_note_reverses_rather_than_merely_weakening() -> None:
    """Above a ratio of one the claim is not a weaker version of itself but its negation.

    Case-folded: the report's own wording capitalises the negation for emphasis, and the
    measurement script's does not, so the test should not pin which of them shouts.
    """
    serious = srn._sigma_agent_note(_metrics(0.5677, 0.4707)).lower()
    registry_before = srn._sigma_agent_note(_metrics(0.1590, 0.5920)).lower()
    assert "do not account" in serious
    assert "account for much" in registry_before


def test_the_generator_and_the_measurement_share_one_ratio() -> None:
    """Two places computing it is two places to get it wrong, so there is one."""
    assert srn._residual_scale is rs


def test_the_note_declines_rather_than_inventing_a_reading() -> None:
    assert srn._sigma_agent_note({}) is None
    assert srn._sigma_agent_note({"tau_mech": {"mean": 0.0}}) is None


def test_the_artefact_records_the_cross_table_reversal() -> None:
    """Not left for a reader to notice: the two tables disagree about the conclusion.

    seriousEvents has no censored cells, so the residual there cannot be an artefact of the
    censoring model -- which is why the reversal is worth recording rather than dismissing.
    """
    path = ROOT / "artifacts" / "residual_scale.json"
    if not path.exists():
        return  # `make residual-scale` has not run in this tree
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert set(doc["tables"]) <= {"other", "serious"}
    assert "reverses_across_tables" in doc
    if len(doc["tables"]) == 2:
        ratios = {k: v["ratio"] for k, v in doc["tables"].items()}
        assert doc["reverses_across_tables"] == (
            (ratios["other"] < 1.0) != (ratios["serious"] < 1.0)
        ), ratios


def test_the_cleavability_scale_is_phrased_from_the_numbers() -> None:
    """"About half the size of the mechanism scale" was the second instance of the defect.

    It was true on the otherEvents table, where the ratio is 0.5293. On seriousEvents it is
    about 0.983 -- effectively the same size -- so the hand-written fraction was not merely at
    risk of going stale, it was already wrong about one of the two tables the report fits.
    """
    half = srn._tau_cleav_note(_metrics_tau(0.2871, 0.5424))
    same = srn._tau_cleav_note(_metrics_tau(0.4629, 0.4707))
    assert "0.5293" in half, half
    # Prefix rather than four digits: the inputs here are the report's rounded means, so
    # the last place differs from the artefact's full-precision ratio.
    assert "0.983" in same, same
    assert "same size" in same and "same size" not in half


def test_the_cleavability_note_states_whether_it_clears_zero() -> None:
    clear = srn._tau_cleav_note(_metrics_tau(0.2871, 0.5424))
    straddling = srn._tau_cleav_note(
        {"tau_mech": {"mean": 0.5, "q05": 0.4, "q95": 0.6},
         "tau_cleav": {"mean": 0.05, "q05": -0.02, "q95": 0.12}}
    )
    assert clear.startswith("the scale") and "Clear of zero" in clear
    assert "Includes zero" in straddling


def test_the_dar_note_reads_its_own_interval() -> None:
    """"Includes zero" is a statement about the interval printed beside it."""
    assert "includes zero" in srn._b_dar_note(
        {"coefficients": {"b_dar": {"mean": 0.0385, "q05": -0.0430, "q95": 0.1220}}}
    )
    moved = srn._b_dar_note(
        {"coefficients": {"b_dar": {"mean": 0.30, "q05": 0.11, "q95": 0.49}}}
    )
    assert "clear of zero" in moved and "includes zero" not in moved


def _metrics_tau(cleav: float, tau: float) -> dict:
    return {
        "tau_mech": {"mean": tau, "q05": tau * 0.8, "q95": tau * 1.2},
        "tau_cleav": {"mean": cleav, "q05": cleav * 0.7, "q95": cleav * 1.4},
    }


def _two_tables(other: float, serious: float) -> tuple[dict, dict]:
    def one(v: float) -> dict:
        return {"coefficients": {"b_thresh": {"mean": v, "q05": v * 0.9, "q95": v * 1.1}}}
    return one(other), one(serious)


def test_the_threshold_note_derives_its_multiple() -> None:
    """"Four times larger on the seriousEvents table" was the argument, hand-written.

    It is the clause that makes `b_thresh` a reporting covariate rather than the censoring
    correction, so of everything in the block it is the one that had to be measured. The
    real value is 3.7318, which "four times" rounded away.
    """
    here, there = _two_tables(0.034092385321855545, 0.12722471356391907)
    note = srn._b_thresh_note(here, there)
    assert "3.7318" in note, note
    assert "times larger on the seriousEvents table" in note


def test_a_sign_flip_is_reported_as_one_not_as_a_multiple() -> None:
    """`b_log_n` does flip sign between the tables, so the shape of the claim matters.

    A ratio of -6.14 stated as "6.14 times larger" would be false in the way that matters:
    the two tables are not measuring the same thing to different degrees.
    """
    here, there = _two_tables(0.0335790179669857, -0.20633620023727417)
    note = srn._b_thresh_note(here, there)
    assert "opposite sign" in note, note
    assert "times larger" not in note


def test_the_note_omits_the_comparison_when_the_other_table_is_absent() -> None:
    here, _ = _two_tables(0.0341, 0.1272)
    note = srn._b_thresh_note(here, None)
    assert note is not None
    assert "absent" in note and "times larger" not in note


def test_the_cross_table_artefact_records_sign_as_well_as_ratio() -> None:
    path = ROOT / "artifacts" / "residual_scale.json"
    if not path.exists():
        return
    across = json.loads(path.read_text(encoding="utf-8")).get("across_tables") or {}
    for name, row in across.items():
        assert row["same_sign"] == ((row["other"] > 0) == (row["serious"] > 0)), name
        # A negative ratio and `same_sign` true would be contradictory, and the report reads
        # one of these two fields to decide how to phrase the claim.
        assert (row["serious_over_other"] > 0) == row["same_sign"], name


def test_the_mechanism_note_states_both_halves_of_the_claim() -> None:
    """Section 4 argues from two things: the scale clears zero, and it is the largest.

    Both are read off the numbers. The second is the one that could change quietly, because
    a corpus where a linker scale overtook the mechanism scale would leave section 4's
    conclusion standing on a sentence that no longer described the fit.
    """
    ok = srn._tau_mech_note(
        {"tau_mech": {"mean": 0.5424, "q05": 0.4494, "q95": 0.6398},
         "tau_cleav": {"mean": 0.2871, "q05": 0.2027, "q95": 0.4133}}
    )
    assert "largest of the design scales" in ok

    overtaken = srn._tau_mech_note(
        {"tau_mech": {"mean": 0.3000, "q05": 0.2000, "q95": 0.4000},
         "tau_cleav": {"mean": 0.7000, "q05": 0.6000, "q95": 0.8000}}
    )
    assert "no longer the largest" in overtaken and "0.7000" in overtaken

    straddling = srn._tau_mech_note({"tau_mech": {"mean": 0.05, "q05": -0.1, "q95": 0.2}})
    assert "includes zero" in straddling and "asserted by the parameter count" in straddling


def test_the_mechanism_note_compares_against_every_design_scale() -> None:
    """`tau_family` is not sampled today, which is why it has to be in the comparison.

    A note that only ever looked at `tau_cleav` would give the right answer now and the
    wrong one the first time the payload-family level was enabled.
    """
    overtaken = srn._tau_mech_note(
        {"tau_mech": {"mean": 0.5424, "q05": 0.4494, "q95": 0.6398},
         "tau_cleav": {"mean": 0.2871, "q05": 0.2027, "q95": 0.4133},
         "tau_family": {"mean": 0.9100, "q05": 0.8000, "q95": 1.0000}}
    )
    assert "no longer the largest" in overtaken and "0.9100" in overtaken


def test_the_denominator_note_reports_the_sign_disagreement() -> None:
    """`b_log_n` is the coefficient whose sign is not shared by the two tables."""
    def one(v):
        return {"coefficients": {"b_log_n": {"mean": v, "q05": v * 0.9, "q95": v * 1.1}}}
    flipped = srn._b_log_n_note(one(0.0336), one(-0.2063))
    assert "opposite sign" in flipped and "-0.2063" in flipped
    agreeing = srn._b_log_n_note(one(0.0336), one(0.0400))
    assert "same sign" in agreeing.lower() and "opposite" not in agreeing
    assert srn._b_log_n_note(one(0.0336), None) is not None
