import csv, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ml"))
import risk_sheet as RS

EV = {"hepatic": (4, 3), "renal": (0, 1), "pulmonary": (1, 7), "otologic": (0, 0)}
CONCEPTS = {"A": ["gpa", ["pulmonary"], "record"], "B": ["pe", ["cardiovascular"], "record"], "C": ["hh", ["hepatic"], "label"], "T": ["test side", [], "record"]}
V51 = {"A": {"pulmonary", "renal"}, "B": {"cardiovascular"}, "C": {"hepatic"}, "T": {"hepatic"}}


def test_disputes_rank_boxed_before_w_and_p():
    d = RS.disputes({"v5.1": {"hepatic", "renal"}, "record": set()}, EV)
    assert d == [("hepatic", 4, 3), ("renal", 0, 1)]


def test_organs_without_any_warning_or_agreement_are_not_disputed():
    assert RS.disputes({"v5.1": {"otologic"}, "record": set()}, EV) == []
    assert RS.disputes({"v5.1": {"hepatic"}, "record": {"hepatic"}}, EV) == []
    assert RS.disputes({"v5.1": {"hepatic"}}, EV) == []


def test_build_orders_by_value_and_leaves_test_side_out():
    rows = RS.build(CONCEPTS, V51, {"B": {"cardiovascular", "pulmonary"}}, {"B"}, [], {"A", "C", "T"}, {"T"}, EV)
    assert [(r["id"], r["organ"]) for r in rows] == [("B", "pulmonary"), ("A", "renal")]
    assert rows[0]["gold"] == ["cardiovascular", "pulmonary"] and rows[0]["record"] == ["cardiovascular"]


def test_sheet_has_blank_answers(tmp_path):
    rows = RS.build(CONCEPTS, V51, {}, set(), [], {"A"}, set(), EV)
    p = tmp_path / "s.csv"; RS.write(rows, str(p))
    r = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    assert len(r) == 1 and r[0]["질환 ID"] == "A" and r[0]["쟁점 장기"] == "renal"
    assert all(r[0][k] == "" for k in RS.HEAD[-3:])
