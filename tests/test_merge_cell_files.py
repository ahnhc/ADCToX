"""The deduplication key decides what counts as the same printed cell.

Three PMC snapshots were fetched with three different agent lists and 25 of the 1,471
articles answer to more than one, so a plain `cat` of the per-snapshot cell files emitted
277 rows twice. The corpus was never affected -- the merge keys observations by (arm, axis,
kind) and a duplicate collapses -- but every per-cell statistic was: `pmc_validation.json`
reported 6,535 paper cells and sized its rate comparison at 1,372 when fewer were distinct.

The key has to be exactly right in both directions, and the interesting half is the second:

* too loose, and a grade-stratified table loses a column. 149 of those 277 "duplicates"
  shared the article, table, row, parent column header, agent and axis while carrying
  *different counts* -- which is what a grade-stratified table looks like once the grade is
  dropped from a truncated column header. A key without `n` and `denominator` would have
  silently deleted the any-grade half of eleven tables.
* too tight, and nothing dedupes: the provenance strings and `is_chosen_source` can differ
  between snapshots for the same printed cell, so a whole-record key keeps both copies.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "merge_cell_files", ROOT / "scripts" / "merge_cell_files.py"
)
merge = importlib.util.module_from_spec(SPEC)
sys.modules["merge_cell_files"] = merge
SPEC.loader.exec_module(merge)


def _cell(**over) -> dict:
    base = {
        "pmcid": "10334227", "table_label": "Table 4",
        "row_label": "Peripheral sensory neuropathy",
        "column_header": "Patients, n (%) All grades",
        "agent": "enfortumab_vedotin", "axis": "neurologic",
        "n": 32, "denominator": 125, "percentage": 25.6,
        "is_chosen_source": True, "row_provenance": "verbatim:pt_dict",
    }
    base.update(over)
    return base


def _run(tmp_path, groups: list[list[dict]]) -> list[dict]:
    paths = []
    for i, rows in enumerate(groups):
        path = tmp_path / f"cells_{i}.jsonl"
        path.write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        paths.append(path)
    out = tmp_path / "all.jsonl"
    argv = sys.argv
    try:
        sys.argv = ["merge_cell_files", *[str(p) for p in paths], "--out", str(out)]
        merge.main()
    finally:
        sys.argv = argv
    return [
        json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_the_same_printed_cell_from_two_snapshots_collapses(tmp_path) -> None:
    a = _cell()
    # The same cell as the other snapshot saw it: provenance and chosen-source differ.
    b = _cell(is_chosen_source=False, row_provenance="rewrite[1]:pt_dict")
    kept = _run(tmp_path, [[a], [b]])
    assert len(kept) == 1, kept


def test_two_grade_strata_under_one_truncated_header_both_survive(tmp_path) -> None:
    """The failure a looser key would cause, which is the one that matters. These two rows
    agree on article, table, row, column header, agent and axis and differ only in the
    count -- the shape a grade-stratified table takes once the grade falls past the header's
    truncation point."""
    any_grade = _cell(n=68, percentage=72.0)
    grade3 = _cell(n=44, percentage=46.0)
    kept = _run(tmp_path, [[any_grade, grade3]])
    assert len(kept) == 2, kept
    assert {c["n"] for c in kept} == {68, 44}


def test_a_different_denominator_is_a_different_cell(tmp_path) -> None:
    """Two arms of one table share a row label and differ in their denominator."""
    kept = _run(tmp_path, [[_cell(denominator=125), _cell(denominator=98, n=28)]])
    assert len(kept) == 2, kept


def test_the_dropped_count_is_reported(tmp_path, capsys) -> None:
    """A growing snapshot overlap is a signal about the fetch lists, and a silent
    deduplication would hide it."""
    _run(tmp_path, [[_cell()], [_cell()]])
    out = capsys.readouterr().out
    assert "dropped as duplicates" in out
    assert " 1 " in out or "1 dropped" in out or "    1" in out


def test_a_missing_input_file_is_skipped_not_fatal(tmp_path) -> None:
    """The Makefile passes the discovery and code-name files through `wildcard`, so they are
    absent on a build that never fetched those snapshots."""
    out = tmp_path / "all.jsonl"
    present = tmp_path / "present.jsonl"
    present.write_text(json.dumps(_cell()) + "\n", encoding="utf-8")
    argv = sys.argv
    try:
        sys.argv = [
            "merge_cell_files", str(present), str(tmp_path / "absent.jsonl"),
            "--out", str(out),
        ]
        merge.main()
    finally:
        sys.argv = argv
    assert len(out.read_text(encoding="utf-8").strip().splitlines()) == 1
