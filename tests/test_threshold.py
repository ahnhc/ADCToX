"""Tests for reporting-threshold recovery.

Filling an unreported event with zero is the error this module exists to prevent, and the
reason it matters is that the bias is correlated rather than random: the cut varies with
the journal and the sponsor, and it varies between tables of the same trial, so a trial
random intercept cannot absorb it. Left alone it reads as a payload effect -- the quantity
the model is estimating.

So the tests are mostly about refusing to produce a zero. Only one phrasing earns a true
zero, and it has to be about frequency.
"""

from __future__ import annotations

import pytest

from adctox.extract.threshold import from_reported_rates, resolve


@pytest.mark.parametrize(
    "caption,expect",
    [
        ("TEAEs occurring in ≥10% of all-treated patients", 10.0),
        ("Adverse events reported in >5% of patients", 5.0),
        ("Adverse events in at least 20% of the safety population", 20.0),
        ("Events reported in more than 2.5% of patients", 2.5),
        ("Adverse events in 15% or more of patients", 15.0),
        ("TEAEs occurring in greater than 7% of patients", 7.0),
    ],
)
def test_an_explicit_cut_is_read_as_a_value_not_a_bound(caption, expect) -> None:
    t = resolve(caption, [expect + 1.0, 40.0])
    assert t.value == expect
    assert t.is_explicit and not t.is_upper_bound


def test_a_grade_threshold_is_not_mistaken_for_a_frequency_one() -> None:
    """"Grade >=3 ... in at least 5%" has two ">=" phrases and only the second is a
    frequency. Reading the first would set the threshold to 3% on a table cut at 5%, and
    the error is invisible because 3 is a plausible frequency."""
    t = resolve("Grade ≥3 adverse events occurring in at least 5% of patients",
                [6.1, 5.2, 22.0])
    assert t.value == 5.0
    assert t.is_explicit


def test_a_grade_threshold_alone_yields_no_frequency_cut() -> None:
    t = resolve("Grade ≥3 treatment-emergent adverse events", [3.0, 11.0])
    assert t.value == 3.0
    assert not t.is_explicit and t.is_upper_bound
    assert t.source == "min_reported_rate"


def test_all_grade_is_a_claim_about_severity_and_never_sets_a_zero() -> None:
    """The mistake this test pins, which I made in the first version. "All-grade adverse
    events" says the table is not restricted to grade 3+. It says nothing about how rare an
    event may be and still appear. Reading it as "no frequency cut" sets the threshold to
    zero, making every absent event a true zero -- the precise error the module exists to
    prevent, reached by over-reading a phrase about something else."""
    t = resolve("All-grade treatment-related adverse events", [0.9, 2.0, 33.0])
    assert t.value == 0.9
    assert t.is_upper_bound and not t.is_explicit
    assert t.all_grade_claimed
    t2 = resolve("Any-grade adverse events", [1.4, 20.0])
    assert t2.value == 1.4 and not t2.is_explicit


def test_a_grade_claim_is_still_recorded_alongside_an_explicit_cut() -> None:
    """The model needs both facts: the table is not grade-filtered, and the cut is 5%."""
    t = resolve("Any-grade AEs occurring in ≥5% of patients", [5.5, 30.0])
    assert t.value == 5.0 and t.is_explicit
    assert t.all_grade_claimed


def test_only_an_explicit_frequency_statement_earns_a_true_zero() -> None:
    """The one case where filling zero is correct: the author says nothing was omitted."""
    for caption in [
        "All adverse events are listed regardless of frequency",
        "Adverse events, irrespective of frequency",
        "No frequency cut-off was applied",
        "All treatment-emergent adverse events are reported",
    ]:
        t = resolve(caption, [0.9, 2.0])
        assert t.value == 0.0, caption
        assert t.is_explicit and not t.is_upper_bound, caption


def test_an_implied_cut_falls_back_to_the_bound_but_records_the_admission() -> None:
    """"Most common adverse events" means a cut was applied. That is worth distinguishing
    from silence, because the bound is then a bound on a real cut."""
    t = resolve("Most common adverse events", [3.2, 8.0, 41.0])
    assert t.value == 3.2
    assert t.is_upper_bound and not t.is_explicit
    assert t.source == "min_reported_rate_after_caption_implied"


def test_silence_falls_back_to_the_minimum_reported_rate() -> None:
    """70.3% of tables. The minimum printed rate bounds the cut from above, because that
    rate got printed."""
    t = resolve("Table 3. Adverse events", [4.1, 9.0, 52.0])
    assert t.value == 4.1
    assert t.is_upper_bound and not t.is_explicit
    assert t.source == "min_reported_rate"


def test_a_printed_rate_below_the_stated_cut_wins() -> None:
    """The caption is a claim about the table; the rates are the table. A footnote
    exempting events of special interest from the cut is common, and trusting the caption
    would censor at 10% a table that demonstrably reports down to 4.2%."""
    t = resolve(
        "Adverse events occurring in ≥10% of patients and events of special interest",
        [4.2, 11.0, 38.0],
    )
    assert t.value == 4.2
    assert t.is_upper_bound and not t.is_explicit
    assert "4.2" in t.evidence and "10" in t.evidence


def test_a_table_with_no_rates_is_unconstrained_rather_than_zero() -> None:
    t = resolve("Table 2. Safety summary", [])
    assert t.value is None
    assert t.source == "unconstrained"
    assert not t.is_explicit


def test_the_bound_is_the_minimum_and_ignores_missing_rates() -> None:
    assert from_reported_rates([]) is None
    assert from_reported_rates([None, 5.0, None, 2.0]).value == 2.0  # type: ignore[list-item]
    # A printed zero means the table shows zeros, so the bound is zero.
    assert from_reported_rates([0.0, 12.0]).value == 0.0


def test_the_bound_direction_is_conservative() -> None:
    """Stated as a test because it is the justification for using a bound at all. The
    derived value is never below the true cut, since the minimum printed rate was printed
    and therefore cleared the cut. Treating the cut as larger than it was widens the
    interval for an unreported event -- it loses power, not correctness."""
    true_cut = 1.0
    printed = [3.2, 8.0, 41.0]        # every printed rate cleared a cut of 1.0
    bound = from_reported_rates(printed)
    assert bound is not None and bound.value >= true_cut
    assert bound.is_upper_bound
