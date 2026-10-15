"""First input screen: disease names suggested as typed, and diseases found from symptoms or a sentence (ml/suggest.py)."""
import pathlib, sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ml"))
import recommend as RC
import suggest as SG


def labels(rows): return [r[2].lower() for r in rows]


@pytest.mark.parametrize("typed, expected", [
    ("간경", "cirrhosis"), ("cirrh", "cirrhosis"), ("ckd", "chronic kidney disease"), ("심부전", "heart failure"),
    ("copd", "chronic obstructive pulmonary disease"), ("ㄱㅎㅇ", "hypertension"), ("diabetis", "diabet"),
])
def test_names_suggest_registry_profiles_korean_abbreviations_initials_and_typos(typed, expected):
    rows = SG.names(RC, typed)
    assert rows and any(expected in l for l in labels(rows)[:5]), labels(rows)
    assert len({(r[0], r[1]) for r in rows}) == len(rows)                  # each concept once


def test_empty_input_suggests_nothing_and_the_last_comma_part_is_searched():
    assert SG.names(RC, "") == [] and SG.names(RC, "   ") == []
    assert any("cirrhosis" in l for l in labels(SG.names(RC, "asthma, 간경")))


@pytest.mark.parametrize("text, expected", [
    ("투석을 일주일에 세 번 하고 있어요", ("kidney", "renal")),
    ("숨이 차고 다리가 부어서 이뇨제를 먹어요", ("heart failure", "cardiac")),
    ("당뇨랑 고혈압이 있어요", ("diabet",)),
])
def test_symptoms_find_the_disease_from_a_sentence_without_models(text, expected):
    rows = SG.symptoms(RC, text, semantic=False, limit=5)
    names = [s[2].lower() for s, _ in rows]
    assert any(any(e in n for e in expected) for n in names), names


def test_profiles_are_complete():
    P = SG.profiles()
    assert len(P) >= 700 and len({p["id"] for p in P}) == len(P)
    for p in P:
        assert p["id"].startswith("MONDO:") and p["ko"] and p["symptoms_en"] and p["symptoms_ko"]


def test_words_that_are_each_a_name_are_offered_separately():
    assert SG.parts(RC, "copd cirrhosis") == ["copd", "cirrhosis"]
    assert SG.parts(RC, "heart failure") == [] and SG.parts(RC, "asthma") == []
