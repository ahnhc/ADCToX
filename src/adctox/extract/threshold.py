"""Recover a table's adverse-event reporting threshold, or bound it.

This is the single most consequential piece of the literature path, and the reason is an
arithmetic trap rather than a modelling preference. A paper's AE table lists the events
above some frequency cut and silently omits the rest. If an omitted event is recorded as
zero, every axis is biased toward zero -- and the bias is not noise, because the cut
correlates with the journal and the sponsor. Nature Medicine prints down to 10%, a
specialty journal prints down to 2%, and sponsors differ in house style. A trial random
intercept cannot absorb it: the bias lives at the *table* level and varies between tables
of the same trial. Left alone it reads as a payload effect, which is exactly the quantity
the model is trying to estimate.

The plan measured the disclosure rate over 202 real captions and footnotes: 70.3% state no
threshold at all, 19.3% state a number, 7.4% say "all grades" with no frequency cut, 3.0%
imply one with "most common". So seven tables in ten need a bound rather than a value.

**The bound is the minimum reported percentage, and it is an upper bound.** A table whose
smallest printed rate is 3.2% had a cut at or below 3.2%, because 3.2% got printed. That
direction is available for every table with at least one rate, which the plan measured at
100%, and it is the conservative direction: using 3.2% when the true cut was 1% treats
more probability mass as possibly-hidden than really was, so an unreported event's rate is
bounded less tightly and the resulting interval is wider rather than narrower. Being wrong
here loses power; the alternative loses correctness.

What this module does not do is guess. A table with no stated cut is marked as bounded, not
as measured, and `is_explicit` travels with the number so a sensitivity analysis can refit
on the 19.3% that stated a cut and report whether the answer moved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "occurring in >=10% of patients", "in at least 5%", "reported in >5% of the safety
# population". The percentage sign is required: a bare ">=10" in a caption is a dose, a
# grade, or a patient count far more often than a frequency.
EXPLICIT_CUT = re.compile(
    r"(?:[≥>]\s*|\bat\s+least\s+|\bmore\s+than\s+|\bgreater\s+than\s+|\bover\s+)"
    r"(?P<pct>\d+(?:\.\d+)?)\s*%",
    re.I,
)
# The same statement written the other way round: "in 10% or more of patients".
EXPLICIT_CUT_TRAILING = re.compile(
    r"(?P<pct>\d+(?:\.\d+)?)\s*%\s*(?:or\s+(?:more|greater|higher)|and\s+above)",
    re.I,
)
# Complete reporting with no frequency cut, stated as such. The wording has to be about
# *frequency*, and this is narrower than it first looks.
#
# "All-grade adverse events" does not belong here, and putting it here was a mistake worth
# naming: it says the table is not restricted to grade 3+, which is a statement about
# severity and says nothing about how rare an event may be and still appear. Reading it as
# "no frequency cut" sets the threshold to zero, which makes every absent event a true
# zero -- the precise error this module exists to prevent, arrived at by over-reading a
# phrase about something else. So a grade claim only strips the grade restriction, and the
# frequency cut still has to be bounded from the printed rates.
NO_FREQUENCY_CUT = re.compile(
    r"regardless\s+of\s+frequency|irrespective\s+of\s+frequency"
    # "All <modifiers> adverse events are reported". The modifier slot is bounded at three
    # words so the pattern cannot bridge a sentence boundary.
    r"|\ball\s+(?:[a-z][a-z-]*\s+){0,3}(?:adverse\s+events?|teaes?|aes?)\s+"
    r"(?:(?:are|were|have\s+been)\s+)?"
    r"(?:listed|shown|reported|included|presented|tabulated)\b"
    r"|no\s+(?:frequency\s+)?(?:cut[-\s]?off|threshold)\s+(?:was\s+)?(?:applied|used)",
    re.I,
)
# A claim about grade only. Recorded because it tells us the table is not grade-filtered,
# which the model needs, but it does not constrain the frequency cut.
ALL_GRADE_CLAIM = re.compile(r"\ball[-\s]grades?\b|\bany[-\s]grade\b", re.I)
# A cut is implied but not stated. Worth distinguishing from silence: "most common" means
# the author applied a cut, so the bound is a bound on a real cut rather than on nothing.
IMPLIED_CUT = re.compile(
    r"\bmost\s+(?:common|frequent)\b|\bcommonest\b|\bselected\s+adverse\s+events?\b",
    re.I,
)
# A phrase that looks like a cut but is not: grade thresholds share the ">=" shape and
# often sit beside a percentage in the same caption.
GRADE_NOT_FREQUENCY = re.compile(r"grade\s*[≥>=]*\s*[1-5]", re.I)


@dataclass(frozen=True)
class Threshold:
    value: float | None        # percentage points; None when nothing constrains it
    is_explicit: bool          # the caption or footnote stated it
    is_upper_bound: bool       # the value bounds the cut rather than equalling it
    source: str                # which rule produced it, for the audit ledger
    evidence: str = ""         # the matched text, for review
    all_grade_claimed: bool = False   # the caption says the table is not grade-filtered


def _strip_grade_phrases(text: str) -> str:
    """Remove grade thresholds before looking for a frequency one.

    "Grade >=3 adverse events occurring in >=5% of patients" contains two ">=" phrases and
    only the second is a frequency. Deleting the grade phrase first is what stops the
    threshold being read as 3.
    """
    return GRADE_NOT_FREQUENCY.sub(" ", text)


def from_caption(text: str) -> Threshold | None:
    """An explicit or implied cut stated in the caption, footnote or label."""
    if not text:
        return None
    cleaned = _strip_grade_phrases(text)
    for pat in (EXPLICIT_CUT, EXPLICIT_CUT_TRAILING):
        m = pat.search(cleaned)
        if m:
            return Threshold(
                value=float(m.group("pct")),
                is_explicit=True,
                is_upper_bound=False,
                source="caption_explicit",
                evidence=m.group(0).strip(),
                all_grade_claimed=bool(ALL_GRADE_CLAIM.search(cleaned)),
            )
    m = NO_FREQUENCY_CUT.search(cleaned)
    if m:
        # Complete reporting at the stated grade. An absent event is a true zero, which is
        # the one case where filling zero is correct.
        return Threshold(
            value=0.0,
            is_explicit=True,
            is_upper_bound=False,
            source="caption_no_cut",
            evidence=m.group(0).strip(),
            all_grade_claimed=bool(ALL_GRADE_CLAIM.search(cleaned)),
        )
    m = IMPLIED_CUT.search(cleaned)
    if m:
        return Threshold(
            value=None,
            is_explicit=False,
            is_upper_bound=True,
            source="caption_implied",
            evidence=m.group(0).strip(),
            all_grade_claimed=bool(ALL_GRADE_CLAIM.search(cleaned)),
        )
    if ALL_GRADE_CLAIM.search(cleaned):
        # Nothing about frequency, so no value -- but record the grade claim so `resolve`
        # can pass it through to the bound it derives from the rates.
        return Threshold(
            value=None,
            is_explicit=False,
            is_upper_bound=False,
            source="caption_all_grade_only",
            evidence=ALL_GRADE_CLAIM.search(cleaned).group(0).strip(),
            all_grade_claimed=True,
        )
    return None


def from_reported_rates(rates: list[float]) -> Threshold | None:
    """The fallback bound: the smallest printed rate is an upper bound on the cut.

    Available for every table carrying at least one rate. A zero among the rates means the
    table prints zeros explicitly, so no cut was applied to the rows it shows and the bound
    is 0 -- which the minimum already gives.
    """
    usable = [r for r in rates if r is not None]
    if not usable:
        return None
    return Threshold(
        value=min(usable),
        is_explicit=False,
        is_upper_bound=True,
        source="min_reported_rate",
        evidence=f"min of {len(usable)} reported rates",
    )


def resolve(caption_text: str, reported_rates: list[float]) -> Threshold:
    """The threshold for one table, preferring a stated cut to a derived bound.

    `reported_rates` must be **one rate per row** -- the row's maximum across columns --
    not every cell in the table. The distinction is the whole correctness of this function,
    and getting it wrong invalidated the first version.

    A reporting cut is a property of *row selection*, not of cell values: an event appears
    in the table because its any-grade rate cleared the cut, and the grade 3-4 sub-rates
    then printed for that already-selected row are routinely 1-5%. Pooling every cell and
    taking the minimum therefore manufactures a contradiction in any table with a grade
    breakdown, which is most of them. Measured: with all cells pooled, 44 of the 45 tables
    whose caption stated a cut were demoted to bounds -- 26.8% of the corpus -- and the
    explicit-threshold rate came out at 0.6% against the plan's measured 19.3%.

    A row maximum below the stated cut is a real contradiction: it means a row was included
    that the stated cut would have excluded, which happens when a footnote exempts events of
    special interest. Then the printed rate wins and the result is marked as a bound,
    because the caption is a claim about the table and the rates are the table.
    """
    stated = from_caption(caption_text)
    derived = from_reported_rates(reported_rates)
    all_grade = bool(stated and stated.all_grade_claimed)

    if stated is not None and stated.value is not None:
        if derived is not None and derived.value is not None and (
            derived.value < stated.value - 1e-9
        ):
            return Threshold(
                value=derived.value,
                is_explicit=False,
                is_upper_bound=True,
                source="min_reported_rate_contradicts_caption",
                evidence=(
                    f"caption said {stated.evidence} but a rate of "
                    f"{derived.value:g}% is printed"
                ),
                all_grade_claimed=all_grade,
            )
        return stated

    if derived is not None:
        # An implied cut plus a derived bound is still just the derived bound, but record
        # that the author admitted to applying one.
        if stated is not None and stated.source in (
            "caption_implied", "caption_all_grade_only"
        ):
            return Threshold(
                value=derived.value,
                is_explicit=False,
                is_upper_bound=True,
                source=f"min_reported_rate_after_{stated.source}",
                evidence=stated.evidence,
                all_grade_claimed=all_grade,
            )
        return Threshold(**{**derived.__dict__, "all_grade_claimed": all_grade})

    return Threshold(
        value=None,
        is_explicit=False,
        is_upper_bound=False,
        source="unconstrained",
        evidence="",
        all_grade_claimed=all_grade,
    )
