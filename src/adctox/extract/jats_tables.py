"""JATS table to a numeric grid, with an arithmetic check on every cell.

The literature path exists because the corpus is agent-limited: 16 agents put the standard
error of a per-axis across-agent rank correlation near 0.28, which is why the project's one
positive signal cannot be settled by analysis. Papers are where more agents are, and their
adverse-event tables are structured XML, not images -- mostly.

Three things in here are load-bearing, and all three were measured by the project plan
before any code existed.

**colspan and rowspan must be expanded.** A `n (%)` cell means nothing until it is bound to
the column header that carries its denominator, and headers routinely span. Measured: the
arithmetic agreement between printed counts and printed percentages falls from 86.8% to
41.3% if spans are ignored. So the grid is materialised cell by cell.

**The arithmetic is the hallucination detector.** By convention these tables print `n (%)`
against a stated N, so `100 * n / N` must reproduce the printed percentage. Measured on
5,930 real cells across 87 tables: 86.8% agree within 0.6 percentage points, 11.3% of
tables state no N anywhere, leaving about 13% needing judgement. A fabricated or
mis-parsed number breaks the identity, so no language model is allowed anywhere near the
digits -- the numbers are parsed deterministically and checked against each other.

**Image-only tables are dropped, never reconstructed.** The plan measured 2.1% of AE tables
as image-only across 239 tables, but that average hides whole journals: every table in
Haematologica's PMC deposit is a `.jpg`. They are reported as a rejection reason with the
journal recorded, so the loss is visible rather than inferred from a thin yield.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

# `n (%)`, `n (%%)`, `n(%)`, and the same with a thousands separator or a decimal percent.
N_PCT = re.compile(
    r"^\s*(?P<n>\d[\d,]*)\s*\(\s*(?P<pct>\d+(?:\.\d+)?)\s*%?\s*\)\s*$"
)
# A bare percentage, which carries no numerator and so cannot be arithmetic-checked.
BARE_PCT = re.compile(r"^\s*(?P<pct>\d+(?:\.\d+)?)\s*%\s*$")
# `n/N`, which states its own denominator.
N_OVER_N = re.compile(r"^\s*(?P<n>\d[\d,]*)\s*/\s*(?P<d>\d[\d,]*)\s*$")
# A denominator in a header: `(N = 123)`, `(n=123)`, `N 123`.
HEADER_N = re.compile(r"[\(\[]?\s*[Nn]\s*[=:]?\s*(?P<d>\d[\d,]*)\s*[\)\]]?")

# Agreement tolerance in percentage points. 0.6 absorbs the printing of a percentage to
# one decimal or to the nearest integer without admitting a wrong numerator.
ARITHMETIC_TOLERANCE_PP = 0.6

AE_CAPTION = re.compile(
    r"adverse|toxicit|\bteae\b|\btrae\b|safety|treatment-emergent|side effect", re.I
)
AE_VOCAB = re.compile(
    r"nausea|vomit|fatigue|an(?:a)?emi|neutropeni|thrombocytopeni|diarrh|rash|alopecia|"
    r"pyrexia|neuropath|keratopath|pneumonitis|transaminas|constipation|stomatitis",
    re.I,
)
GRADE_TOKEN = re.compile(r"grade\s*[≥>=]*\s*[1-5]|grade\s*3|all[- ]grade", re.I)


def _text(node) -> str:
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


@dataclass
class Cell:
    row: int
    col: int
    text: str
    n: int | None = None
    pct: float | None = None
    denominator: int | None = None
    arithmetic_ok: bool | None = None
    arithmetic_delta_pp: float | None = None


@dataclass
class ParsedTable:
    label: str
    caption: str
    footer: str
    n_rows: int
    n_cols: int
    header_rows: int
    column_denominators: dict[int, int] = field(default_factory=dict)
    row_labels: dict[int, str] = field(default_factory=dict)
    cells: list[Cell] = field(default_factory=list)
    is_image_only: bool = False
    looks_like_ae_table: bool = False

    @property
    def checkable(self) -> list[Cell]:
        return [c for c in self.cells if c.arithmetic_ok is not None]

    @property
    def arithmetic_pass_rate(self) -> float | None:
        ch = self.checkable
        return (sum(c.arithmetic_ok for c in ch) / len(ch)) if ch else None


def _grid(table) -> tuple[list[list[str]], int]:
    """Materialise a JATS `<table>` into a dense grid, expanding spans.

    Returns the grid and how many leading rows are header rows. `rowspan` is tracked as a
    carry so a spanning cell occupies every row it covers, which is what makes a row label
    recoverable when a stub cell spans several adverse-event rows.
    """
    rows = table.findall(".//tr")
    grid: list[list[str]] = []
    carry: dict[int, tuple[str, int]] = {}
    header_rows = 0
    for r_i, tr in enumerate(rows):
        row: list[str] = []
        col = 0
        in_head = tr.getparent() is not None and etree.QName(tr.getparent()).localname == "thead"
        if in_head:
            header_rows = max(header_rows, r_i + 1)
        for cellnode in tr.findall("./*"):
            name = etree.QName(cellnode).localname
            if name not in ("td", "th"):
                continue
            while col in carry:
                text, left = carry.pop(col)
                row.append(text)
                if left > 1:
                    carry[col] = (text, left - 1)
                col += 1
            text = _text(cellnode)
            try:
                cspan = max(1, int(cellnode.get("colspan", 1)))
                rspan = max(1, int(cellnode.get("rowspan", 1)))
            except ValueError:
                cspan = rspan = 1
            for _ in range(cspan):
                while col in carry:
                    t2, l2 = carry.pop(col)
                    row.append(t2)
                    if l2 > 1:
                        carry[col] = (t2, l2 - 1)
                    col += 1
                row.append(text)
                if rspan > 1:
                    carry[col] = (text, rspan - 1)
                col += 1
        while col in carry:
            text, left = carry.pop(col)
            row.append(text)
            if left > 1:
                carry[col] = (text, left - 1)
            col += 1
        grid.append(row)
    width = max((len(r) for r in grid), default=0)
    for r in grid:
        r.extend([""] * (width - len(r)))
    # A table with no <thead> still usually has one header row: the row carrying the
    # denominators. Treating it as data would parse "(N = 123)" as a count.
    if header_rows == 0 and grid and any(HEADER_N.search(c) for c in grid[0]):
        header_rows = 1
    return grid, header_rows


def _column_denominators(grid: list[list[str]], header_rows: int) -> dict[int, int]:
    out: dict[int, int] = {}
    for r in range(min(header_rows, len(grid))):
        for c, text in enumerate(grid[r]):
            m = HEADER_N.search(text)
            if m:
                out[c] = int(m.group("d").replace(",", ""))
    return out


def parse_table_wrap(wrap) -> ParsedTable:
    label = _text(wrap.find("./label")) if wrap.find("./label") is not None else ""
    cap = wrap.find(".//caption")
    caption = _text(cap) if cap is not None else ""
    foots = wrap.findall(".//table-wrap-foot") + wrap.findall(".//fn")
    footer = " ".join(_text(f) for f in foots)
    table = wrap.find(".//table")
    blob = " ".join([label, caption, footer, _text(wrap)])
    looks_ae = bool(
        AE_CAPTION.search(" ".join([label, caption, footer]))
        or (GRADE_TOKEN.search(blob) and len(AE_VOCAB.findall(blob)) >= 2)
    )
    if table is None or not table.findall(".//tr"):
        return ParsedTable(
            label=label, caption=caption, footer=footer, n_rows=0, n_cols=0,
            header_rows=0, is_image_only=bool(wrap.findall(".//graphic")),
            looks_like_ae_table=looks_ae,
        )

    grid, header_rows = _grid(table)
    denoms = _column_denominators(grid, header_rows)
    out = ParsedTable(
        label=label, caption=caption, footer=footer,
        n_rows=len(grid), n_cols=(len(grid[0]) if grid else 0),
        header_rows=header_rows, column_denominators=denoms,
        looks_like_ae_table=looks_ae,
    )
    for r in range(header_rows, len(grid)):
        row = grid[r]
        # The row label is the first non-numeric cell, which is the stub column.
        for text in row:
            if text and not N_PCT.match(text) and not BARE_PCT.match(text):
                out.row_labels[r] = text
                break
        for c, text in enumerate(row):
            cell = Cell(row=r, col=c, text=text)
            m = N_PCT.match(text)
            if m:
                cell.n = int(m.group("n").replace(",", ""))
                cell.pct = float(m.group("pct"))
                cell.denominator = denoms.get(c)
                if cell.denominator:
                    implied = 100.0 * cell.n / cell.denominator
                    cell.arithmetic_delta_pp = abs(implied - cell.pct)
                    cell.arithmetic_ok = (
                        cell.arithmetic_delta_pp <= ARITHMETIC_TOLERANCE_PP
                    )
            else:
                m2 = N_OVER_N.match(text)
                if m2:
                    cell.n = int(m2.group("n").replace(",", ""))
                    cell.denominator = int(m2.group("d").replace(",", ""))
                else:
                    m3 = BARE_PCT.match(text)
                    if m3:
                        cell.pct = float(m3.group("pct"))
                        cell.denominator = denoms.get(c)
            out.cells.append(cell)
    return out


def parse_article(path) -> tuple[dict, list[ParsedTable]]:
    root = etree.parse(str(path)).getroot()
    at = root.find(".//article-title")
    jt = root.find(".//journal-title")
    meta = {
        "article_type": root.get("article-type"),
        "title": _text(at) if at is not None else "",
        "journal": _text(jt) if jt is not None else "",
    }
    return meta, [parse_table_wrap(w) for w in root.findall(".//table-wrap")]
