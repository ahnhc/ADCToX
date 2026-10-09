"""Turn one parsed adverse-event table into attributed arm-axis cells.

This is where the project's largest measured risk lives. The plan tried detecting an
agent's papers loosely and found 52 of 54 agents had "an extractable AE table"; requiring
the agent's name in the title and a primary-report signature left 13. The other 39 were
review articles carrying *other drugs'* AE tables. A 75% false-positive rate, and the
failure is silent: a misattributed table does not look wrong, it looks like data, and one
of them corrupts every row of an agent that may have only a handful of papers.

So attribution here is deterministic and refuses more than it accepts, along two axes.

**Table level.** A table naming a different known ADC in any column header is a
comparison, and comparisons are rejected whole rather than split. Keeping the agent's
column and dropping the comparator's sounds safe, but it depends on having read the header
correctly, and that is the one thing a misattribution means you did not do.

**Column level.** A data column has to be resolvable to the agent, to a named comparator,
or to a pooled total. Anything else makes the column ambiguous, and one ambiguous data
column rejects the table. A two-arm table where the arms cannot be told apart is worse
than no table: it contributes a plausible rate to the wrong arm, and no downstream check
can detect it, because the arithmetic gate verifies that a count matches its percentage,
not that it belongs to the drug.

What this does not attempt is the dose. A column reading "ADC 1.8 mg/kg (N = 54)" carries
a dose, and the corpus does model dose -- but a paper's dose string is free text and
getting it wrong silently shifts a dose coefficient, so dose stays a separate problem and
these cells carry the string unparsed for a later, measured pass.
"""

from __future__ import annotations

import functools
import pathlib
import re
from dataclasses import dataclass, field

import yaml

from .jats_tables import Cell, ParsedTable
from .row_labels import MappedRow, map_row
from .threshold import Threshold, resolve as resolve_threshold

# Column headers that are a pooled total rather than an arm. For a monotherapy paper these
# are usable and are what ClinicalTrials.gov reports anyway.
TOTAL_HEADER = re.compile(
    r"\b(?:total|overall|all\s+patients|all\s+treated|pooled|combined"
    r"|safety\s+(?:population|set|analysis\s+set)|entire\s+cohort)\b",
    re.I,
)
# Named comparators. Rejected as columns, but their presence does not reject the table --
# a randomised ADC-versus-chemotherapy trial is a legitimate source for the ADC's arm.
COMPARATOR_HEADER = re.compile(
    r"\b(?:placebo|control|comparator|chemotherapy|physician'?s?\s+choice|tpc"
    r"|standard\s+of\s+care|soc\s+arm|best\s+supportive\s+care"
    r"|observation|untreated|vehicle)\b",
    re.I,
)
COMBINATION_CONF = (
    pathlib.Path(__file__).resolve().parents[3] / "conf" / "ontology"
    / "combination_partners.yaml"
)


@functools.lru_cache(maxsize=1)
def combination_pattern(conf: pathlib.Path = COMBINATION_CONF) -> re.Pattern[str]:
    """A column naming a combination partner is a combination arm.

    Needed because a combination rate belongs to neither drug alone, and the corpus models
    combination as a binary covariate rather than as a shared row. Without it,
    "Enfortumab vedotin + pembrolizumab (N = 440)" attributes to enfortumab and the EV-302
    combination profile enters the corpus as monotherapy. Regimen acronyms are matched too,
    because haematology headers name the regimen rather than its parts.
    """
    doc = yaml.safe_load(conf.read_text(encoding="utf-8"))
    names = sorted(
        (str(x).strip().lower() for x in doc["partners"] + doc["regimens"]),
        key=len, reverse=True,
    )
    # Regimen acronyms carry `+` and digits, so the boundary has to be non-alphanumeric
    # rather than \b -- `\bA+AVD\b` does not match what it looks like it matches.
    alts = "|".join(re.escape(n) for n in names if n)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alts})(?![A-Za-z0-9])", re.I)


# A column that is not a patient group at all.
NON_ARM_HEADER = re.compile(
    r"\b(?:p[-\s]?value|hazard\s+ratio|odds\s+ratio|95%\s*ci|difference"
    r"|rate\s+ratio|relative\s+risk|grade|severity|soc|system\s+organ\s+class"
    r"|event|term|toxicity|adverse\s+event)\b",
    re.I,
)


@dataclass(frozen=True)
class ColumnAttribution:
    col: int
    header: str
    kind: str          # 'agent' | 'comparator' | 'total' | 'non_arm' | 'ambiguous'
    reason: str
    denominator: int | None = None
    dose_text: str = ""     # carried unparsed; see the module note


@dataclass
class ExtractedCell:
    agent: str
    axis: str
    row_label: str
    normalized_term: str
    n: int
    denominator: int
    percentage: float | None
    arithmetic_ok: bool | None
    column_header: str
    column_kind: str
    row_provenance: str


@dataclass
class TableExtraction:
    accepted: bool
    reason: str
    cells: list[ExtractedCell] = field(default_factory=list)
    threshold: Threshold | None = None
    columns: list[ColumnAttribution] = field(default_factory=list)
    rows: list[MappedRow] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)


def attribute_column(
    header: str,
    col: int,
    denominator: int | None,
    agent_aliases: set[str],
    other_agent_aliases: dict[str, set[str]],
) -> ColumnAttribution:
    """Resolve one column header to an arm, a comparator, a total, or ambiguity."""
    low = header.lower()
    hits = {
        other for other, aliases in other_agent_aliases.items()
        if any(a in low for a in aliases)
    }
    mine = any(a in low for a in agent_aliases)

    if hits and not mine:
        return ColumnAttribution(col, header, "ambiguous",
                                 f"names another agent: {sorted(hits)}", denominator)
    if hits and mine:
        return ColumnAttribution(col, header, "ambiguous",
                                 f"names this agent and {sorted(hits)}", denominator)
    combo = combination_pattern().search(header)
    if combo and mine:
        return ColumnAttribution(
            col, header, "ambiguous",
            f"combination arm: this agent with {combo.group(0)!r}", denominator,
        )
    if COMPARATOR_HEADER.search(header):
        return ColumnAttribution(col, header, "comparator", "named comparator",
                                 denominator)
    if combo:
        # A partner named without our agent is somebody else's arm.
        return ColumnAttribution(col, header, "comparator",
                                 f"other regimen: {combo.group(0)!r}", denominator)
    if mine:
        return ColumnAttribution(col, header, "agent", "agent named in header",
                                 denominator, dose_text=header)
    if TOTAL_HEADER.search(header):
        return ColumnAttribution(col, header, "total", "pooled total", denominator)
    if denominator is None:
        return ColumnAttribution(col, header, "non_arm", "no denominator", None)
    if NON_ARM_HEADER.search(header):
        return ColumnAttribution(col, header, "non_arm", "statistic column", denominator)
    return ColumnAttribution(col, header, "ambiguous",
                             "denominator but unidentifiable header", denominator)


def extract(
    table: ParsedTable,
    agent: str,
    agent_aliases: set[str],
    other_agent_aliases: dict[str, set[str]],
    taxonomy,
    column_headers: dict[int, str] | None = None,
) -> TableExtraction:
    """Extract attributed cells from one table, or decline and say why.

    `column_headers` overrides the table's own joined headers, which exists for tests and
    for the case where a caller has resolved an arm name the header does not carry.
    """
    counters: dict[str, int] = {}

    def bump(key: str, by: int = 1) -> None:
        counters[key] = counters.get(key, 0) + by

    if table.is_image_only:
        return TableExtraction(False, "image_only", counters={"image_only": 1})
    if not table.cells:
        return TableExtraction(False, "empty_grid", counters={"empty_grid": 1})

    cols = sorted({c.col for c in table.cells})
    attributions = [
        attribute_column(
            (column_headers or {}).get(col) or table.column_header(col),
            col, table.column_denominators.get(col),
            agent_aliases, other_agent_aliases,
        )
        for col in cols
    ]
    by_col = {a.col: a for a in attributions}

    # One ambiguous data column rejects the table. A column with no denominator cannot
    # carry a rate, so it cannot be the ambiguity that matters.
    ambiguous = [
        a for a in attributions if a.kind == "ambiguous" and a.denominator is not None
    ]
    if ambiguous:
        bump("rejected_ambiguous_column", len(ambiguous))
        return TableExtraction(
            False,
            "ambiguous_column: " + "; ".join(
                f"col {a.col} ({a.header[:40]!r}): {a.reason}" for a in ambiguous[:3]
            ),
            columns=attributions,
            counters=counters,
        )

    usable_cols = [
        a.col for a in attributions
        if a.kind in ("agent", "total") and a.denominator is not None
    ]
    if not usable_cols:
        bump("rejected_no_usable_column")
        return TableExtraction(False, "no_usable_column", columns=attributions,
                               counters=counters)

    rows: list[MappedRow] = []
    cells: list[ExtractedCell] = []
    rates: list[float] = []
    by_row: dict[int, list[Cell]] = {}
    for c in table.cells:
        by_row.setdefault(c.row, []).append(c)

    for row_idx in sorted(by_row):
        label = table.row_labels.get(row_idx, "")
        mapped = map_row(label, taxonomy)
        rows.append(mapped)
        bump(f"row_{mapped.kind}")
        # Rates are collected from every row, aggregate rows included: the reporting cut
        # applies to the whole table, and an aggregate row's rate still cleared it.
        for c in by_row[row_idx]:
            if c.col in usable_cols and c.pct is not None:
                rates.append(c.pct)
        if mapped.kind != "pt" or mapped.axis.startswith("__"):
            continue
        for c in by_row[row_idx]:
            if c.col not in usable_cols or c.n is None:
                continue
            denom = by_col[c.col].denominator
            if denom is None:
                continue
            bump("cells_extracted")
            cells.append(ExtractedCell(
                agent=agent,
                axis=mapped.axis,
                row_label=label,
                normalized_term=mapped.normalized,
                n=c.n,
                denominator=denom,
                percentage=c.pct,
                arithmetic_ok=c.arithmetic_ok,
                column_header=by_col[c.col].header,
                column_kind=by_col[c.col].kind,
                row_provenance=mapped.provenance,
            ))

    caption_blob = " ".join([table.label, table.caption, table.footer])
    threshold = resolve_threshold(caption_blob, rates)

    if not cells:
        bump("rejected_no_mapped_rows")
        return TableExtraction(False, "no_mapped_rows", threshold=threshold,
                               columns=attributions, rows=rows, counters=counters)

    return TableExtraction(True, "ok", cells=cells, threshold=threshold,
                           columns=attributions, rows=rows, counters=counters)
