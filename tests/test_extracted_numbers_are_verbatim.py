"""Every extracted number must be findable in the paper it is attributed to.

The plan requires this and the arithmetic gate does not supply it. That gate checks
`100 * n / N` against the printed percentage, which catches a cell whose two numbers
disagree -- but if the parser read the wrong column outright, `n` and the percentage come
from the same wrong cell, agree perfectly, and the gate passes. The same is true of an
off-by-one row: a rate attributed to the wrong organ is internally consistent.

So this checks the binding rather than the arithmetic: the cell's printed text and its row
label must occur in the same `table-wrap` of the PMCID the cell names. That is the claim
the corpus actually makes about each number, and it is the one no downstream statistic can
recover if it is wrong.
"""

from __future__ import annotations

import json
import pathlib
import random
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CELLS = pathlib.Path("/data/hyeongchanahn/adctox/processed/all_cells.jsonl")
XML_DIRS = [
    pathlib.Path("/data/hyeongchanahn/adctox/raw/pmc/2026-10-07/xml"),
    pathlib.Path("/data/hyeongchanahn/adctox/raw/pmc/2026-10-07-discovery/xml"),
    pathlib.Path("/data/hyeongchanahn/adctox/raw/pmc/2026-10-07-codename/xml"),
]
# Sampled rather than exhaustive: 6,535 cells across 1,400 articles would re-parse the
# whole corpus, and a transcription fault is systematic rather than scattered -- a parser
# that mis-binds one cell mis-binds a class of them.
SAMPLE = 120
SEED = 20261009

pytestmark = pytest.mark.skipif(
    not CELLS.exists(), reason="run `make pmc-extract`"
)


def _xml_for(pmcid: str) -> pathlib.Path | None:
    for d in XML_DIRS:
        p = d / f"PMC{pmcid}.xml"
        if p.exists():
            return p
    return None


def _table_texts(path: pathlib.Path) -> list[str]:
    """Each `table-wrap`'s full text, whitespace-normalised, from the raw XML."""
    from lxml import etree

    root = etree.parse(str(path)).getroot()
    return [
        re.sub(r"\s+", " ", "".join(w.itertext()))
        for w in root.findall(".//table-wrap")
    ]


@pytest.fixture(scope="module")
def sample() -> list[dict]:
    rows = [
        json.loads(line)
        for line in CELLS.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert rows, "no extracted cells"
    rng = random.Random(SEED)
    return rng.sample(rows, min(SAMPLE, len(rows)))


def test_the_sample_is_broad_enough_to_mean_something(sample) -> None:
    """A sample drawn from one article, one agent or one denominator source would pass the
    checks below while testing almost nothing. Measured on the current corpus: 120 cells
    span 68 articles, 25 agents and all 14 axes, with 100 header denominators and 20
    inferred-and-corroborated ones -- so the inference path is exercised rather than
    assumed."""
    assert len({c["pmcid"] for c in sample}) >= 20
    assert len({c["agent"] for c in sample}) >= 8
    assert len({c["axis"] for c in sample}) >= 8
    sources = {c.get("denominator_source") for c in sample}
    assert "inferred_corroborated" in sources, (
        "the sample contains no inferred denominator, so the verbatim check does not test "
        "the inference path -- raise SAMPLE or reseed"
    )


def test_the_source_article_is_on_disk_for_every_sampled_cell(sample) -> None:
    """A cell naming a PMCID whose XML is absent cannot be checked by anything."""
    missing = sorted({c["pmcid"] for c in sample if _xml_for(c["pmcid"]) is None})
    assert not missing, missing[:10]


def test_each_number_and_its_row_label_share_a_table(sample) -> None:
    """The binding, not the arithmetic. The count, the percentage and the row label must
    all appear in one `table-wrap` of the cited paper."""
    failures: list[str] = []
    cache: dict[str, list[str]] = {}
    for cell in sample:
        pmcid = cell["pmcid"]
        if pmcid not in cache:
            path = _xml_for(pmcid)
            cache[pmcid] = _table_texts(path) if path else []
        tables = cache[pmcid]
        label = re.sub(r"\s+", " ", str(cell["row_label"])).strip()
        n = str(cell["n"])
        # A table carrying the count, the row label and -- when one was printed -- the
        # percentage. The percentage is checked as a substring of its own formatting,
        # since papers write 40, 40.0 and 40.00 for the same value.
        pct = cell.get("percentage")
        ok = False
        for text in tables:
            if label and label not in text:
                continue
            if n not in text:
                continue
            if pct is None:
                ok = True
                break
            if any(
                form in text
                for form in {f"{pct:g}", f"{pct:.1f}", f"{pct:.0f}", f"{pct:.2f}"}
            ):
                ok = True
                break
        if not ok:
            failures.append(
                f"PMC{pmcid} {cell['table_label']} "
                f"row={label[:40]!r} n={n} pct={pct} axis={cell['axis']}"
            )
    assert not failures, (
        f"{len(failures)} of {len(sample)} sampled cells could not be found in their own "
        "source table:\n  " + "\n  ".join(failures[:10])
    )


def test_the_denominator_appears_in_the_article(sample) -> None:
    """A denominator is either printed in the column header or inferred and corroborated
    elsewhere in the article, so it must appear in the article's text either way. An
    inferred denominator that appears nowhere would mean the corroboration check passed on
    a value the paper never states."""
    from lxml import etree

    failures: list[str] = []
    cache: dict[str, str] = {}
    for cell in sample:
        pmcid = cell["pmcid"]
        if pmcid not in cache:
            path = _xml_for(pmcid)
            cache[pmcid] = (
                re.sub(r"\s+", " ", "".join(etree.parse(str(path)).getroot().itertext()))
                if path else ""
            )
        text = cache[pmcid]
        denom = str(cell["denominator"])
        if denom not in text:
            failures.append(
                f"PMC{pmcid} denominator {denom} "
                f"(source: {cell.get('denominator_source')})"
            )
    assert not failures, (
        f"{len(failures)} denominators absent from their article:\n  "
        + "\n  ".join(failures[:10])
    )


def test_a_fabricated_count_would_be_caught(sample) -> None:
    """Guards the guard. The checks above pass; this shows they can fail, which a check
    built on `any(... in text ...)` can easily stop doing."""
    cell = sample[0]
    path = _xml_for(cell["pmcid"])
    assert path is not None
    tables = _table_texts(path)
    label = re.sub(r"\s+", " ", str(cell["row_label"])).strip()
    assert any(label in t and str(cell["n"]) in t for t in tables), cell
    assert not any(label in t and "999991" in t for t in tables)
