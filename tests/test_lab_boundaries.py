"""x ULN and Cockcroft-Gault values reach the label thresholds unrounded; only the screen rounds them."""
import sys, pathlib
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ml"))
import labs as LB
import restrictions as RS


def _holds(when, raw):
    lab = LB.derive(raw)[0]
    return RS._holds(when, lab, RS.Patient(**lab))


@pytest.mark.parametrize("bili, above", [(3.599, False), (3.6, False), (3.601, True)])
def test_bilirubin_at_three_times_uln(bili, above):
    """ULN 1.2 mg/dL: 3.601 is above 3 x ULN (it used to round to 3.0 and count as 'up to 3 x ULN')."""
    assert _holds({"bili_gt": 3}, {"bilirubin": bili}) is above
    assert _holds({"bili_gt": 1.5, "bili_le": 3}, {"bilirubin": bili}) is not above


@pytest.mark.parametrize("bili, category", [(3.599, "monitor"), (3.6, "monitor"), (3.601, "insufficient_data")])
def test_datopotamab_hepatic_rule_at_the_boundary(bili, category):
    import recommend as RC
    rows, *_ = RC.recommend([], {}, {"bilirubin": bili})
    row = next(r for r in rows if r["name"].startswith("Datopotamab"))
    assert [reason[3] for reason in RC.reason_rows(row) if reason[0] == "hepatic"] == [category]


@pytest.mark.parametrize("key, uln_times, when", [("ast", 2.5, "ast_gt"), ("ast", 3, "ast_gt"), ("alt", 2.5, "alt_gt")])
@pytest.mark.parametrize("delta, above", [(-0.01, False), (0, False), (0.01, True)])
def test_ast_alt_at_their_thresholds(key, uln_times, when, delta, above):
    value = LB.ULN[key] * uln_times + delta                          # 40 U/L ULN: 99.99, 100, 100.01 for 2.5 x ULN
    assert _holds({when: uln_times}, {key: value}) is above


@pytest.mark.parametrize("creatinine, below", [(1.999, False), (2.0, False), (2.001, True)])
def test_cockcroft_gault_at_crcl_30(creatinine, below):
    raw = {"age": 68, "weight": 60, "creatinine": creatinine, "sex": "M"}  # (140 - 68) x 60 / (72 x 2.0) = 30 exactly
    assert _holds({"crcl_lt": 30}, raw) is below and _holds({"crcl_ge": 30}, raw) is not below


def test_cockcroft_gault_female_factor_is_exact():
    raw = {"age": 40, "weight": 43.2, "creatinine": 1.7, "sex": "F"}     # 100 x 43.2 / 122.4 x 0.85 = 30
    assert LB.derive(raw)[0]["crcl"] == 30.0 and _holds({"crcl_ge": 30}, raw) is True


def test_organ_flags_compare_exactly():
    assert LB.derive({"bilirubin": 1.8})[1] == []                    # 1.5 x 1.2 is 1.8: not above
    assert LB.derive({"bilirubin": 1.801})[1] == [("hepatic", "bilirubin > 1.5 x ULN (CTCAE G2)")]
    assert LB.derive({"ast": 120})[1] == [] and LB.derive({"ast": 120.01})[1]


def test_only_the_screen_rounds():
    lab, _, notes = LB.derive({"bilirubin": 3.601, "age": 70, "weight": 61, "creatinine": 1.3, "sex": "M"})
    assert lab["bili"] == 3.601 / 1.2 and round(lab["crcl"], 6) == round(70 * 61 / (72 * 1.3), 6)
    assert LB.shown("bili", lab["bili"]) == "3.001"                 # not '3': that is the other side of 3 x ULN
    assert LB.shown("bili", 3.599 / 1.2) == "2.999" and LB.shown("bili", 3.0) == "3" and LB.shown("bili", 2.04) == "2.04"
    assert LB.shown("crcl", 29.96) == "29.96" and LB.shown("crcl", 62.3456) == "62.3"
    assert notes[0] == f"CLcr {LB.shown('crcl', lab['crcl'])} mL/min (Cockcroft-Gault)"


def test_key_values_show_the_rounded_value():
    import recommend as RC
    rows, _, notes, _ = RC.recommend([], {}, {"bilirubin": 3.601})
    text = "\n".join(RC._result_context(rows, notes, 100, {"bili": LB.derive({"bilirubin": 3.601})[0]["bili"]}))
    assert "Bilirubin 3.001×ULN" in text
