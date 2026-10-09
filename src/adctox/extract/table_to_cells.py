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
import itertools
import pathlib
import re
from dataclasses import dataclass, field

import yaml

from .denominator import InferredDenominator, fill as fill_denominators
from .jats_tables import HEADER_N, Cell, ParsedTable
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
#
# Two misses found by validating against the registry, and both put chemotherapy toxicity
# into the corpus as ADC toxicity. "Physician's choice" was in the pattern but papers write
# it with a typographic apostrophe (U+2019), which `'?` does not match -- so headers are
# apostrophe-normalised before the search rather than the pattern being widened. And "SoC"
# appears bare, not only as "SoC arm".
COMPARATOR_HEADER = re.compile(
    r"\b(?:placebo|control|comparator|chemotherapy|chemo"
    r"|physician'?s?\s+choice|investigator'?s?\s+choice|tpc"
    r"|standard\s+of\s+care|soc|best\s+supportive\s+care|bsc"
    r"|observation|untreated|vehicle)\b",
    re.I,
)
# Typographic punctuation, normalised before any pattern runs. A curly apostrophe reading
# as a different character from a straight one is the kind of difference that silently
# changes which arm a rate belongs to.
TYPOGRAPHIC = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
    "\u00a0": " ", "\u2212": "-",
})
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


# A header joining two treatments with "+". Structural, because the enumerated partner list
# will always be behind: validating against the registry caught "Pola + BR (N = 35)" --
# polatuzumab plus bendamustine-rituximab -- entering the corpus as polatuzumab
# monotherapy, because "BR" is a regimen abbreviation no list had. A combination rate
# belongs to neither drug alone, so any "+" between two treatment-looking words makes the
# column a combination regardless of whether either name is recognised.
#
# The exclusions are the places "+" means something else: a grade or dose ceiling
# ("Grade 3+"), a receptor status ("HR+", "HER2+"), and a line count ("2+ prior lines").
COMBINATION_PLUS = re.compile(
    r"(?<![A-Za-z0-9])(?![\s]*(?:grade|mg|kg|prior|line|year|mo\b|month))"
    r"[A-Za-z][A-Za-z0-9-]{1,}\s*\+\s*"
    r"(?!\s*(?:\d|grade|mg/kg))[A-Za-z][A-Za-z0-9-]{1,}",
    re.I,
)
RECEPTOR_STATUS = re.compile(
    r"\b(?:hr|her2|er|pr|pd-?l1|cd\d+|egfr|trop-?2)\s*\+", re.I
)

# A caption naming serious events as the table's *subject*. Distinct from the row
# "Serious adverse events", which is an aggregate inside a common-events table -- the same
# four words mean different things in the two positions.
#
# Which table a set of cells belongs to matters because the two rank organs differently
# (measured mean rho +0.1455 on the registry corpus) and the model fits them separately,
# with `serious` treated as complete reporting. A table misfiled as `serious` would have
# its unreported axes recorded as true zeros instead of censored.
SERIOUS_TABLE = re.compile(
    # Modifiers go on either side of "serious": captions write both "serious
    # treatment-related adverse events" and "treatment-related serious adverse events".
    r"\b(?:[a-z][a-z-]*\s+){0,2}serious\s+(?:[a-z][a-z-]*\s+){0,2}"
    r"(?:adverse\s+events?|teaes?|aes?)\b",
    re.I,
)
# ... and the phrases that mean the table is the common-events one even though "serious"
# appears somewhere in it. Checked first, because a caption reading "adverse events
# occurring in >=10% of patients, including serious adverse events" is a common-events
# table that happens to mention the word.
COMMON_TABLE_OVERRIDE = re.compile(
    r"occurring\s+in\s*[\u2265>]|\bin\s+[\u2265>]\s*\d|\ball[-\s]grades?\b"
    r"|\bany[-\s]grade\b|\btreatment[-\s]emergent\s+adverse\s+events?\b",
    re.I,
)


def table_kind(table: ParsedTable) -> str:
    """'serious' or 'other', matching the registry's two event tables."""
    blob = " ".join([table.label, table.caption, table.footer])
    if COMMON_TABLE_OVERRIDE.search(blob):
        return "other"
    return "serious" if SERIOUS_TABLE.search(blob) else "other"


# A column that is not a patient group at all.
#
# Deliberately narrow, and it used to be the opposite. The first version also claimed
# `grade`, `event`, `term`, `toxicity`, `severity`, `soc` and `adverse event` -- which
# threw away most of the corpus, because a two-row header joins the arm name to the grade
# label and arrives as "N = 57 Any grade", "Induction (n = 44) Grade 3/4" or
# "PTCL (n = 33) Any grade". Those are arms. Measured cost of the mistake: of 405 AE tables
# rejected for having no usable column, 56 were legitimate arm groups discarded this way.
#
# The words are unnecessary as well as harmful. A stub column and a grade-label column have
# no denominator, so the denominator check above already excludes them; a p-value or a
# hazard-ratio column never carries an `N =`. So this pattern only has to name the
# statistics that could somehow acquire one.
NON_ARM_HEADER = re.compile(
    r"\b(?:p[-\s]?value|hazard\s+ratio|odds\s+ratio|rate\s+ratio|relative\s+risk"
    r"|95%\s*ci|confidence\s+interval|difference)\b",
    re.I,
)


@dataclass(frozen=True)
class ColumnAttribution:
    col: int
    header: str
    kind: str          # 'agent' | 'comparator' | 'total' | 'non_arm' | 'ambiguous'
    reason: str
    denominator: int | None = None
    denominator_source: str = "header"   # 'header' | 'inferred_corroborated'
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
    denominator_source: str = "header"


@dataclass
class TableExtraction:
    accepted: bool
    reason: str
    cells: list[ExtractedCell] = field(default_factory=list)
    threshold: Threshold | None = None
    kind: str = "other"
    columns: list[ColumnAttribution] = field(default_factory=list)
    rows: list[MappedRow] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)


# Everything after the arm name in a two-row header: the grade label, the cell-format note,
# and the subgroup qualifier. Stripping it leaves the arm identity, which is what decides
# whether two columns describe the same arm.
_ARM_NAME_TAIL = re.compile(
    r"\b(?:any[-\s]grade|all[-\s]grades?|grade\s*[\u2265\u2a7e>=<\u2264\u2a7d]*\s*[0-5]"
    r"(?:\s*[-/]\s*[0-5])?|no\.?\s*\(\s*%\s*\)|n\s*\(\s*%\s*\)|%|total)\b.*$",
    re.I,
)


def _arm_identity(header: str) -> str:
    """The part of a header that names the arm, with the denominator and grade removed."""
    out = HEADER_N.sub(" ", header.translate(TYPOGRAPHIC))
    out = _ARM_NAME_TAIL.sub(" ", out)
    return re.sub(r"[^a-z0-9]+", " ", out.lower()).strip()


def _subgroup_columns(attributions: list[ColumnAttribution]) -> set[int]:
    """Columns that name a subset of another column's arm.

    Two relationships count, and the second is the one that matters in practice.

    *Same arm name, different denominators.* The largest is the arm; the rest are subsets.

    *One arm name extending another.* "Brentuximab vedotin" and "Brentuximab vedotin CD30
    < 10%" do not share an identity string, so the first rule leaves the subgroup in place
    -- it only ever compares subgroups with each other. The subset shows itself as a token
    prefix: the broader column's identity is a prefix of the narrower one's, and the
    narrower one's denominator is smaller. That is what catches "Phase I (n = 28)" beside
    an arm of 37, and "Japanese population" beside the full population.

    A header with no arm name at all -- the title-attribution case -- gives no evidence
    either way and is left alone.
    """
    scored: list[tuple[int, tuple[str, ...], int]] = []
    for a in attributions:
        if a.denominator is None or a.kind not in ("agent", "total", "agent_by_title"):
            continue
        ident = tuple(_arm_identity(a.header).split())
        if not ident:
            continue
        scored.append((a.col, ident, a.denominator))

    out: set[int] = set()
    for col, ident, denom in scored:
        for other_col, other_ident, other_denom in scored:
            if other_col == col:
                continue
            same = other_ident == ident and other_denom > denom
            extends = (
                len(other_ident) < len(ident)
                and ident[: len(other_ident)] == other_ident
                and other_denom > denom
            )
            if same or extends:
                out.add(col)
                break
    return out


# How many columns a partition may have. Beyond this the subset search is both slow and
# prone to coincidence, and real stratifications in these tables are two to five cells.
_MAX_PARTITION_PARTS = 5


def _nested_denominator_columns(
    attributions: list[ColumnAttribution],
) -> set[int]:
    """Columns whose header states more than one denominator.

    A two-row header that joins "SG (n = 243)" to "*1/*1 wild type (n = 113)" declares the
    arm and then a stratum of it in the same string. `_column_denominators` keeps the last
    match, so the column carries 113 and the parent 243 never becomes a column of its own --
    which puts both the subgroup rule and the partition rule out of reach, since neither can
    see a parent that is not a column.

    Two `N =` statements in one header is the signal itself, and it needs no parent column:
    the outer one is the population the column belongs to and the inner one is the subset
    being reported. Found by validating against the registry, where the UGT1A1 genotype
    strata of one sacituzumab arm (113, 96 and 34 against a registry arm of 258) all
    carried a header that also said 243.
    """
    out: set[int] = set()
    for a in attributions:
        if a.denominator is None:
            continue
        if a.kind not in ("agent", "total", "agent_by_title"):
            continue
        if len(HEADER_N.findall(a.header.translate(TYPOGRAPHIC))) >= 2:
            out.add(a.col)
    return out


def _partition_columns(attributions: list[ColumnAttribution]) -> set[int]:
    """Columns whose denominators partition another column's in the same table.

    The subgroup rule above needs the subgroup's header to extend its parent's, which fails
    whenever the strata are named independently -- "Normal (BMI 18.5 to <25) n = 117" and
    "Obese (BMI >=30) n = 66" beside a safety population of 258 share no arm name with it.
    Validating against the registry surfaced these as a run of denominator mismatches, all
    smaller than the registry's.

    Arithmetic identifies them without reading the labels: if several columns' denominators
    sum exactly to another column's, they are a stratification of it. Admitting them as
    arms would put two or more correlated partial populations into the corpus under one
    trial, and the hierarchical model would read their agreement as independent evidence.

    Only in-table denominators are used as the parent. A sum matching an N stated elsewhere
    in the article identifies a partition too, but with no parent column there is nothing to
    keep instead, and dropping the only data available is a worse answer than a flagged
    population mismatch.
    """
    usable = [
        a for a in attributions
        if a.denominator is not None
        and a.kind in ("agent", "total", "agent_by_title")
    ]
    by_denominator: dict[int, list[int]] = {}
    for a in usable:
        by_denominator.setdefault(a.denominator, []).append(a.col)
    distinct = sorted(by_denominator)
    if len(distinct) < 3:
        return set()

    out: set[int] = set()
    for parent in reversed(distinct):          # largest first
        parts = [d for d in distinct if d < parent]
        for size in range(2, min(_MAX_PARTITION_PARTS, len(parts)) + 1):
            match = next(
                (c for c in itertools.combinations(parts, size) if sum(c) == parent),
                None,
            )
            if match:
                for d in match:
                    out.update(by_denominator[d])
                break
    # A column cannot be both a parent and a part: if the arithmetic says otherwise the
    # table is not a partition and nothing is dropped.
    parents = {
        c for d, cols in by_denominator.items() for c in cols if c not in out
    }
    return out - parents if parents else set()


def attribute_column(
    header: str,
    col: int,
    denominator: int | None,
    agent_aliases: set[str],
    other_agent_aliases: dict[str, set[str]],
    title_names_agent: bool = False,
) -> ColumnAttribution:
    """Resolve one column header to an arm, a comparator, a total, or ambiguity.


    `title_names_agent` enables the plan's second attribution path: "the agent in the title
    **or** an explicit column binding". A single-arm paper's AE table header is often just
    "N = 57 Any grade" or "Induction (n = 44)", naming the arm but not the drug, because the
    drug is in the title. Rejecting those cost 56 legitimate arm groups out of 405 rejected
    tables, so a denominator column that names nothing recognisable is attributed to the
    agent -- but only when the caller has established that no other known ADC appears
    anywhere in the table, and only under its own `agent_by_title` kind so the looser path
    is counted separately and cannot launder the stricter one's precision.
    """
    header = header.translate(TYPOGRAPHIC)
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
    if combo is None and not RECEPTOR_STATUS.search(header):
        structural = COMBINATION_PLUS.search(header)
        if structural:
            return ColumnAttribution(
                col, header, "ambiguous",
                f"combination arm (joined by '+'): {structural.group(0)!r}", denominator,
            )
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
    if title_names_agent:
        return ColumnAttribution(col, header, "agent_by_title",
                                 "title names the agent and no other ADC is in the table",
                                 denominator, dose_text=header)
    return ColumnAttribution(col, header, "ambiguous",
                             "denominator but unidentifiable header", denominator)


def extract(
    table: ParsedTable,
    agent: str,
    agent_aliases: set[str],
    other_agent_aliases: dict[str, set[str]],
    taxonomy,
    column_headers: dict[int, str] | None = None,
    sibling_tables: list[ParsedTable] | None = None,
    title_names_agent: bool = False,
) -> TableExtraction:
    """Extract attributed cells from one table, or decline and say why.

    `column_headers` overrides the table's own joined headers, which exists for tests and
    for the case where a caller has resolved an arm name the header does not carry.

    `title_names_agent` says the article's title names this agent, which enables the
    second attribution path -- see `attribute_column`. It is only honoured for tables where
    no other known ADC is named, and that check is made here rather than left to the caller.

    `sibling_tables` are the article's other tables, used to recover a denominator the
    header does not state. 44% of the usable AE tables in the measured sample are in that
    position, and the recovery requires the article to corroborate the inferred integer --
    see extract/denominator.py for why both steps are needed.
    """
    counters: dict[str, int] = {}
    by_col_source: dict[int, str] = {}

    def bump(key: str, by: int = 1) -> None:
        counters[key] = counters.get(key, 0) + by

    kind = table_kind(table)
    if table.is_image_only:
        return TableExtraction(False, "image_only", kind=kind,
                               counters={"image_only": 1})
    if not table.cells:
        return TableExtraction(False, "empty_grid", kind=kind,
                               counters={"empty_grid": 1})

    # The title path is only safe on a table that mentions no other known ADC anywhere --
    # header, caption, label or footnote. A review's comparison table names the other drugs
    # in its caption even when the columns do not, and that is the 75% false-positive trap.
    table_blob = " ".join(
        [table.label, table.caption, table.footer]
        + [table.column_header(c) for c in sorted({cc.col for cc in table.cells})]
    ).translate(TYPOGRAPHIC).lower()
    foreign = sorted(
        other for other, aliases in other_agent_aliases.items()
        if any(a in table_blob for a in aliases)
    )
    use_title = title_names_agent and not foreign
    if title_names_agent and foreign:
        bump("title_path_blocked_by_foreign_agent")

    cols = sorted({c.col for c in table.cells})
    inferred: dict[int, InferredDenominator] = (
        fill_denominators(table, sibling_tables) if sibling_tables else {}
    )
    for col, got in inferred.items():
        bump("denominator_inferred")
        _ = got
    attributions = [
        attribute_column(
            (column_headers or {}).get(col) or table.column_header(col),
            col,
            table.column_denominators.get(col)
            or (inferred[col].value if col in inferred else None),
            agent_aliases, other_agent_aliases, title_names_agent=use_title,
        )
        for col in cols
    ]
    for a in attributions:
        if a.col in inferred and a.col not in table.column_denominators:
            by_col_source[a.col] = "inferred_corroborated"
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
            kind=kind,
            columns=attributions,
            counters=counters,
        )

    # Subgroup columns, found by validating against the registry. A table reporting
    # "Brentuximab vedotin (n = 50) CD30 < 10%" alongside "... CD30 >= 10%" has two columns
    # naming one arm with denominators of 22 and 28 against the registry's 66. Both are
    # real data about subsets of one arm, and admitting them as arms would put two
    # correlated partial populations into the corpus under one trial and understate the
    # arm's size -- which the registry comparison showed directly, as a run of denominator
    # mismatches all smaller than the registry's.
    #
    # The signal is structural rather than lexical: the qualifier wording is unbounded
    # ("CD30min < 10%", "Phase I", "Japanese population", "EORTC evaluable"), but a column
    # that names the same arm as another column while carrying a *different* denominator
    # can only be a subset of it.
    subgroup_cols = (
        _subgroup_columns(attributions)
        | _partition_columns(attributions)
        | _nested_denominator_columns(attributions)
    )
    for col in subgroup_cols:
        bump("column_dropped_as_subgroup")

    usable_cols = [
        a.col for a in attributions
        if a.kind in ("agent", "total", "agent_by_title")
        and a.denominator is not None
        and a.col not in subgroup_cols
    ]
    for a in attributions:
        if a.kind == "agent_by_title" and a.col in usable_cols:
            bump("column_attributed_by_title")
    if not usable_cols:
        bump("rejected_no_usable_column")
        return TableExtraction(False, "no_usable_column", kind=kind,
                               columns=attributions, counters=counters)

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
        # One rate per row -- the row's maximum across the usable columns -- because a
        # reporting cut selects rows by their any-grade rate and the grade 3-4 sub-rates of
        # an already-selected row routinely fall below it. Pooling every cell instead
        # manufactures a contradiction in any table with a grade breakdown; see
        # extract/threshold.py. Aggregate rows are included, since their rate cleared the
        # cut too.
        row_rates = [
            c.pct for c in by_row[row_idx]
            if c.col in usable_cols and c.pct is not None
        ]
        if row_rates:
            rates.append(max(row_rates))
        if mapped.kind != "pt" or mapped.axis.startswith("__"):
            continue
        for c in by_row[row_idx]:
            if c.col not in usable_cols or c.n is None:
                continue
            denom = by_col[c.col].denominator
            if denom is None:
                continue
            bump("cells_extracted")
            arith = c.arithmetic_ok
            if arith is None and c.pct is not None:
                # The cell was parsed before this denominator was recovered, so the gate
                # never ran on it. Running it now is not circular: the inference required
                # the article to state this integer independently, so the check is against
                # a number the cell did not supply.
                arith = abs(100.0 * c.n / denom - c.pct) <= 0.6
            cells.append(ExtractedCell(
                agent=agent,
                axis=mapped.axis,
                row_label=label,
                normalized_term=mapped.normalized,
                n=c.n,
                denominator=denom,
                percentage=c.pct,
                arithmetic_ok=arith,
                column_header=by_col[c.col].header,
                column_kind=by_col[c.col].kind,
                row_provenance=mapped.provenance,
                denominator_source=by_col_source.get(c.col, "header"),
            ))

    caption_blob = " ".join([table.label, table.caption, table.footer])
    threshold = resolve_threshold(caption_blob, rates)

    if not cells:
        bump("rejected_no_mapped_rows")
        return TableExtraction(False, "no_mapped_rows", threshold=threshold, kind=kind,
                               columns=attributions, rows=rows, counters=counters)

    return TableExtraction(True, "ok", cells=cells, threshold=threshold, kind=kind,
                           columns=attributions, rows=rows, counters=counters)
