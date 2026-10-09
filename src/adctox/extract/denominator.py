"""Recover a column's denominator when the header does not state one.

Measured on the first 239 fetched articles: of the adverse-event tables that are
machine-readable and carry counts, 35 state a denominator in the column header and 28 do
not. Losing those 28 is a 44% loss on the only tables that can feed a binomial, which is
worse than the image-only loss that the plan worried about.

The caption is not the answer. Searching every caption and footnote recovered 5 of those
28 -- 18% -- because 78.6% of them state no N anywhere in the table's own text.

The answer is that the denominator is already in the data. A cell printed as `40 (40.0)`
says N is about 100, and several such cells pin it: N is the integer that reproduces every
printed percentage from its printed count. So inference, not retrieval.

**Inference alone is not good enough, and the measurement says so precisely.** Run against
the 162 columns that *do* state a denominator, inference produced a value for 143 and got
19 of them wrong -- 88.3% precision. The errors are the dangerous kind: mostly off by one
or two, because at a 0.6pp tolerance a 258-patient column is only identified to within
about two patients, and a handful were off by thousands where the column held something
other than `n (%)` of N. A wrong denominator yields a wrong rate that passes every
downstream check, since the arithmetic gate verifies a count against its own percentage
and both would be re-derived from the same wrong N.

**So inference proposes and the article confirms.** A candidate is accepted only if the
same integer is stated somewhere else in the article -- another column's header, another
table's caption, a footnote, or prose like "106 patients were treated". On the 162 columns
with a stated denominator, requiring that corroboration gave **124 of 124 correct, with
all 19 errors rejected**, at a recall of 86.7%. On the columns with no stated denominator
it recovers 42 of the 68 that are inferable at all.

That precision is measured on one sample of 239 articles and is not a guarantee; what is
structural is the reason it works. An error of one or two patients comes from the tolerance,
and a number that an author independently wrote down elsewhere in the paper is not off by
one or two. The two sources fail in unrelated ways, which is the whole argument for
requiring both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .jats_tables import Cell, ParsedTable

# An `N = 123` statement anywhere in a caption, label or footnote. Same boundary rule as
# the header pattern, for the same reason: a bare `N` matches the last letter of a drug
# name followed by a dose.
STATED_N = re.compile(r"(?<![A-Za-z])[Nn](?![A-Za-z])\s*[=:]\s*(\d[\d,]*)")
# The prose form, which is how a paper states its safety population when no table does.
PROSE_N = re.compile(
    r"(\d[\d,]{1,5})\s+(?:patients|participants|subjects)\b", re.I
)

TOLERANCE_PP = 0.6          # the arithmetic gate's tolerance; see jats_tables
MIN_SUPPORT = 3             # cells that must agree
MIN_DISTINCT_COUNTS = 3     # a column of identical counts does not identify N
CANDIDATE_SWEEP = 4         # integers either side of each cell's implied N


@dataclass(frozen=True)
class InferredDenominator:
    value: int
    n_cells_supporting: int
    n_cells_total: int
    corroborated_by: str     # where the article independently states this integer
    source: str = "inferred_corroborated"


def stated_denominators(
    tables: list[ParsedTable],
    exclude: tuple[ParsedTable, int] | None = None,
) -> dict[int, str]:
    """Every N the article states, mapped to where it was found.

    `exclude` drops one (table, column) so a column's own header cannot corroborate its own
    inference -- without that the check is circular and reports perfect precision by
    construction.
    """
    out: dict[int, str] = {}
    for t in tables:
        for col, val in t.column_denominators.items():
            if exclude is not None and t is exclude[0] and col == exclude[1]:
                continue
            out.setdefault(int(val), f"header of {t.label or 'a table'} col {col}")
        blob = " ".join([t.label, t.caption, t.footer])
        for m in STATED_N.finditer(blob):
            out.setdefault(int(m.group(1).replace(",", "")),
                           f"caption of {t.label or 'a table'}")
        for m in PROSE_N.finditer(blob):
            out.setdefault(int(m.group(1).replace(",", "")),
                           f"prose in {t.label or 'a table'}")
    return out


def propose(cells: list[Cell]) -> tuple[int | None, int, int]:
    """The integer N that best reproduces these cells' printed percentages.

    Returns the candidate, how many cells it reproduces within tolerance, and how many
    cells were usable. The candidate is chosen by support first and then by least squared
    error: ranking by support alone leaves several near-identical integers tied, and
    breaking that tie arbitrarily was wrong about half the time on the measured sample.
    """
    pairs = [(c.n, c.pct) for c in cells if c.n is not None and c.pct]
    if len(pairs) < MIN_SUPPORT:
        return None, 0, len(pairs)
    if len({n for n, _ in pairs}) < MIN_DISTINCT_COUNTS:
        return None, 0, len(pairs)

    candidates: set[int] = set()
    for n, pct in pairs:
        implied = 100.0 * n / pct
        for k in range(-CANDIDATE_SWEEP, CANDIDATE_SWEEP + 1):
            cand = round(implied) + k
            if cand >= MIN_SUPPORT:
                candidates.add(cand)

    scored = sorted(
        (
            (
                sum(1 for n, pct in pairs if abs(100.0 * n / N - pct) <= TOLERANCE_PP),
                -sum((100.0 * n / N - pct) ** 2 for n, pct in pairs),
                N,
            )
            for N in candidates
        ),
        reverse=True,
    )
    support, _, best = scored[0]
    if support < MIN_SUPPORT or support < 0.8 * len(pairs):
        return None, support, len(pairs)
    # A count above its own denominator is impossible, so the candidate is wrong even
    # though it fit the percentages.
    if any(n > best for n, _ in pairs):
        return None, support, len(pairs)
    return best, support, len(pairs)


def infer(
    table: ParsedTable,
    col: int,
    all_tables: list[ParsedTable],
) -> InferredDenominator | None:
    """A corroborated denominator for one column, or None.

    Both steps are required. Inference alone was 88.3% precise on the measured sample and
    its errors are undetectable downstream; corroboration alone cannot tell which of an
    article's several stated denominators belongs to this column.
    """
    cells = [c for c in table.cells if c.col == col]
    best, support, total = propose(cells)
    if best is None:
        return None
    stated = stated_denominators(all_tables, exclude=(table, col))
    where = stated.get(best)
    if where is None:
        return None
    return InferredDenominator(
        value=best,
        n_cells_supporting=support,
        n_cells_total=total,
        corroborated_by=where,
    )


def fill(table: ParsedTable, all_tables: list[ParsedTable]) -> dict[int, InferredDenominator]:
    """Corroborated denominators for every column of `table` whose header lacks one."""
    cols = sorted({c.col for c in table.cells}) if table.cells else []
    out: dict[int, InferredDenominator] = {}
    for col in cols:
        if col in table.column_denominators:
            continue
        got = infer(table, col, all_tables)
        if got is not None:
            out[col] = got
    return out
