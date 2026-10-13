"""ml/team_sheets.py imports a filled organ sheet from one reviewer as well as from two."""
import csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
import team_sheets as TS

SHEET = ROOT / "data/curated/team_sheets/1_장기판정_검토.csv"


def filled(tmp_path, name, marks):
    """a copy of the blank organ sheet with {row index: {column: 'O'}} filled in, saved as Excel would (UTF-8 BOM)."""
    rows = list(csv.DictReader(open(SHEET, encoding="utf-8-sig")))
    for i, cols in marks.items(): rows[i].update(cols)
    p = tmp_path / name
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return p, rows


def labels(tmp_path):
    out = list((tmp_path / "concept_organs/labels").glob("expert_team_*.jsonl"))
    assert len(out) == 1
    return [json.loads(x) for x in open(out[0], encoding="utf-8")]


def test_one_reviewer_organ_sheet_becomes_labels(tmp_path, monkeypatch):
    (tmp_path / "concept_organs/labels").mkdir(parents=True); monkeypatch.setattr(TS, "CUR", tmp_path)
    p, rows = filled(tmp_path, "1_김철수.csv", {0: {"신경": "O", "대사내분비": "O", "검토자": "김철수"}, 1: {"해당 장기 없음": "O"}, 2: {"모르겠음": "O"}})
    TS.organs([p])
    got = {x["id"]: x for x in labels(tmp_path)}
    assert set(got) == {rows[0]["질환 ID (수정 금지)"], rows[1]["질환 ID (수정 금지)"]}          # 'unclear' is not a label
    a = got[rows[0]["질환 ID (수정 금지)"]]
    assert a["organs"] == ["neurologic", "metabolic_endocrine"] and a["scope"] == "axis" and a["confidence"] == "single" and a["reviewer"] == "김철수"
    assert got[rows[1]["질환 ID (수정 금지)"]]["scope"] == "no_axis"


def test_two_reviewers_keep_only_agreeing_rows(tmp_path, monkeypatch):
    (tmp_path / "concept_organs/labels").mkdir(parents=True); monkeypatch.setattr(TS, "CUR", tmp_path)
    monkeypatch.setattr(TS, "SHEETS", tmp_path)
    a, rows = filled(tmp_path, "A.csv", {0: {"간": "O"}, 1: {"폐": "O"}})
    b, _ = filled(tmp_path, "B.csv", {0: {"간": "O"}, 1: {"신장": "O"}})
    TS.organs([a, b])
    got = labels(tmp_path)
    assert [x["id"] for x in got] == [rows[0]["질환 ID (수정 금지)"]] and got[0]["confidence"] == "high"
    assert list(tmp_path.glob("1_장기판정_불일치_*.csv"))
