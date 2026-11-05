"""From the judge's raw output to what the user reads: numbered subtypes, the choice screen, the patient's cancer, the two-tier gate.
The judge is stubbed with rows the real one gives (the stated measurements are in the commit messages)."""
import sys
from pathlib import Path

import pytest

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "ml"), str(Path(__file__).resolve().parents[1] / "src")]
import recommend as RC
import scratch_runtime as SR
import subtypes as ST

HCM = "MONDO:0005045"; HCM3 = "MONDO:0007267"; CMT = "MONDO:0015626"
TABLE = {HCM: ("hypertrophic cardiomyopathy", ["cardiovascular"], "label"), CMT: ("Charcot-Marie-Tooth disease", ["neurologic", "musculoskeletal"], "label")}


def row(concept, name, organs, sim=0.9, valid=1.0, others=(), judged=("renal",)):
    """a row of scratch_runtime.judge; others: more (concept, name, organs, sim)"""
    cand = [dict(concept=concept, name=name, organs=list(organs), via="label", sim=sim)] + [dict(concept=c, name=n, organs=list(o), via="label", sim=s) for c, n, o, s in others]
    return dict(concept=concept, name=name, organs=list(organs), via="label", valid=valid, ok=True, sim=sim, p={}, judged=list(judged), candidates=cand)


@pytest.fixture
def judged(monkeypatch):
    """reads(text -> judge row) -> resolve([text]) as (how, organs), and the link"""
    monkeypatch.setattr(SR, "available", lambda: True); monkeypatch.setattr(SR, "concept", lambda c, path=None: TABLE.get(c))
    monkeypatch.setattr(RC, "english", lambda texts: list(texts))
    def reads(rows):
        monkeypatch.setattr(SR, "judge", lambda texts: [rows[t] for t in texts]); RC._FREE.clear(); RC._ANALYSES.clear()
        return lambda t: (dict(RC.resolve([t])[3])[t], RC.resolve([t])[1], RC._free_info([t])[0])
    yield reads
    RC._FREE.clear(); RC._ANALYSES.clear()


@pytest.mark.parametrize("name, parsed", [("hypertrophic cardiomyopathy 3", ("hypertrophic cardiomyopathy", "3")),
                                          ("hypothyroidism, congenital, nongoitrous, 7", ("hypothyroidism, congenital, nongoitrous", "7")),
                                          ("Charcot-Marie-Tooth disease, axonal, type 2FF", ("Charcot-Marie-Tooth disease, axonal", "2FF")),
                                          ("Maturity-onset diabetes of the young type 8", ("Maturity-onset diabetes of the young", "8")),
                                          ("glycogen storage disease II", ("glycogen storage disease", "II")),
                                          ("type 2 diabetes mellitus", None), ("vitamin B12 deficiency", None), ("COVID-19", None), ("factor V deficiency", None),
                                          ("factor V", None), ("HER2", None), ("trisomy 21", None), ("chronic kidney disease stage 3", None), ("chromosome X", None)])
def test_a_numbered_subtype_is_told_from_a_name_that_has_a_number(name, parsed):
    assert ST.parse(name) == parsed


@pytest.mark.parametrize("subtype, general", [("hypertrophic cardiomyopathy 3", "hypertrophic cardiomyopathy"), ("hemochromatosis type 1", "hereditary hemochromatosis"),
                                              ("Pulmonary hypertension, primary, 1", "idiopathic pulmonary arterial hypertension"), ("hypercholesterolemia, familial, 1", "familial hypercholesterolemia"),
                                              ("Charcot-Marie-Tooth disease, axonal, type 2FF", "Charcot-Marie-Tooth disease"), ("Maturity-onset diabetes of the young type 8", "maturity-onset diabetes of the young"),
                                              ("primary biliary cholangitis 3", "primary biliary cholangitis")])
def test_the_table_names_each_subtypes_general_concept(subtype, general):
    rows = {v[0].lower(): v[2] for v in ST.general_map().values()}
    assert rows[subtype.lower()].lower() == general.lower()


@pytest.mark.parametrize("typed, name, kept", [("hypertrophic cardiomyopathy 3", "hypertrophic cardiomyopathy 3", True), ("MODY 3", "maturity-onset diabetes of the young type 3", True),
                                               ("LQT3", "long QT syndrome 3", True), ("Gaucher type III", "Gaucher disease type 3", True), ("샤르코 2형", "Charcot-Marie-Tooth disease type 2", True),
                                               ("hemochromatosus", "hemochromatosis type 1", False), ("CHF NYHA III", "hypertrophic cardiomyopathy 3", False), ("long QT 7", "long QT syndrome 3", False)])
def test_a_subtype_stays_only_when_the_text_names_it(typed, name, kept):
    assert ST.keeps(typed, name) is kept


def test_a_read_of_a_subtype_nobody_typed_becomes_the_general_concept_with_its_organs(judged):
    read = judged({"HCM": row(HCM3, "hypertrophic cardiomyopathy 3", ["neurologic"]), "hypertrophic cardiomyopathy 3": row(HCM3, "hypertrophic cardiomyopathy 3", ["neurologic"]),
                   "CHF NYHA III": row(HCM3, "hypertrophic cardiomyopathy 3", ["neurologic"])})
    how, organs, link = read("HCM")
    assert "'hypertrophic cardiomyopathy'" in how and organs == {"cardiovascular"} and link["mondo"] == HCM
    assert read("hypertrophic cardiomyopathy 3")[2]["mondo"] == HCM3
    assert read("CHF NYHA III")[2]["mondo"] == HCM


def test_without_a_general_concept_a_close_plain_candidate_wins_else_the_subtype_stays(judged, monkeypatch):
    numbered = next(k for k, v in ST.general_map().items() if v[1] is None); name = ST.general_map()[numbered][0]
    read = judged({"close": row(numbered, name, ["renal"], 0.90, others=[("MONDO:9", "plain disease", ["ocular"], 0.89)]),
                   "far": row(numbered, name, ["renal"], 0.90, others=[("MONDO:9", "plain disease", ["ocular"], 0.80)])})
    assert read("close")[2]["mondo"] == "MONDO:9" and read("far")[2]["mondo"] == numbered


def test_a_general_read_keeps_what_most_of_its_subtypes_have_where_its_label_is_narrower(judged, monkeypatch):
    table = {HCM: ("hypertrophic cardiomyopathy", ["cardiovascular"], "label")}
    subtypes = [k for k, v in ST.general_map().items() if v[1] == HCM]
    table.update({k: ("subtype", ["cardiovascular", "hepatic"] if n % 2 else ["hepatic"], "label") for n, k in enumerate(subtypes)})
    table[subtypes[0]] = ("subtype", ["cardiovascular", "hepatic", "renal"], "label")
    monkeypatch.setattr(SR, "concept", lambda c, path=None: table.get(c)); RC._GENERAL_ORGANS.clear()
    read = judged({"HCM": row(HCM3, "hypertrophic cardiomyopathy 3", ["renal"])})
    monkeypatch.setattr(SR, "concept", lambda c, path=None: table.get(c)); RC._GENERAL_ORGANS.clear()
    assert read("HCM")[1] == {"cardiovascular", "hepatic"}
    RC._GENERAL_ORGANS.clear()


def _rows(*concepts): return [("mondo", c, ST.general_map()[c][0] if c in ST.general_map() else c, "", []) for c in concepts]


@pytest.mark.parametrize("q, listed", [("hypertrophic cardiomyopathy", [HCM, "MONDO:1"]),                                 # the general concept in its subtypes' place, once
                                       ("hypertrophic cardiomyopathy type", [HCM3, "MONDO:0008647", "MONDO:1"]),           # the word type alone names any of them
                                       ("hypertrophic cardiomyopathy 3", [HCM3, HCM, "MONDO:0008647", "MONDO:1"])])         # the one typed, then the general concept
def test_a_list_hides_subtypes_unless_the_text_has_a_number_or_the_word_type(q, listed):
    import suggest as SG
    rows = _rows(HCM3, "MONDO:0008647", "MONDO:1")
    assert [s[1] for s in SG._subtypes_rule(q, rows, lambda g: ("mondo", g, "general", "", []))] == listed


def test_a_list_keeps_a_subtype_without_a_general_concept_last():
    import suggest as SG
    numbered = next(k for k, v in ST.general_map().items() if v[1] is None)
    assert [s[1] for s in SG._subtypes_rule("abc", _rows(numbered, "MONDO:1"), lambda g: None)] == ["MONDO:1", numbered]


SCD = row("MONDO:0007374", "Schnyder corneal dystrophy", ["ocular"], 1.0, others=[("MONDO:0011382", "sickle cell disease", ["haematologic"], 0.7), ("MONDO:2", "other", ["ocular"], 0.69)])


def test_a_short_input_whose_candidates_disagree_gets_the_choice_screen(judged, monkeypatch):
    monkeypatch.setattr(RC, "_abbreviations", lambda text: [])
    read = judged({"SCD": SCD})
    _, _, link = read("SCD")
    assert link["ambiguous"] and [o["mondo"] for o in link["readings"]] == ["MONDO:0007374", "MONDO:0011382", "MONDO:2"]
    assert RC.ambiguous_conditions(["SCD"]) == [("SCD", link["readings"])]
    assert link["readings"][1] == dict(mondo="MONDO:0011382", name="sickle cell disease", organs=["haematologic"], why="similar name")


def test_a_short_input_is_also_offered_what_it_abbreviates_and_a_name_once(judged, monkeypatch):
    monkeypatch.setattr(RC, "_abbreviations", lambda text: [dict(concept="MONDO:7", name="sickle cell disease", organs=["haematologic"], why="abbreviation")])
    read = judged({"SCD": row("MONDO:1", "a", ["ocular"], 1.0, others=[("HP:2", "A", [], 0.9)])})
    link = read("SCD")[2]
    assert [(o["mondo"], o["why"]) for o in link["readings"]] == [("MONDO:1", "closest name"), ("MONDO:7", "abbreviation")] and link["ambiguous"]


def test_a_longer_input_is_a_choice_only_for_tied_candidates_with_other_organs(judged, monkeypatch):
    monkeypatch.setattr(RC, "_abbreviations", lambda text: [])
    read = judged({"long name far": row("MONDO:1", "a", ["ocular"], 0.95, others=[("MONDO:2", "b", ["renal"], 0.90)]),
                   "long name tied": row("MONDO:1", "a", ["ocular"], 0.95, others=[("MONDO:2", "b", ["renal"], 0.94)]),
                   "long name same": row("MONDO:1", "a", ["ocular"], 0.95, others=[("MONDO:2", "b", ["ocular"], 0.94)]),
                   "abc": row("MONDO:1", "a", ["ocular"], 0.95, others=[("MONDO:2", "b", ["ocular"], 0.80), ("MONDO:3", "c", [], 0.70)])})
    assert not read("long name far")[2]["ambiguous"] and read("long name tied")[2]["ambiguous"]
    assert not read("long name same")[2]["ambiguous"] and not read("abc")[2]["ambiguous"]      # no organs is no disagreement


def test_a_korean_name_is_not_a_short_input(judged):
    read = judged({"당뇨병": row("MONDO:1", "a", ["ocular"], 0.95, others=[("MONDO:2", "b", ["renal"], 0.80)])})
    assert not read("당뇨병")[2]["ambiguous"]


def test_a_weak_match_asks_to_confirm_the_read_in_the_review(judged):
    read = judged({"weak": row("MONDO:1", "a", ["ocular"], 0.79), "strong": row("MONDO:1", "a", ["ocular"], 0.80)})
    assert read("weak")[2]["doubt"] == "confirm" and read("strong")[2]["doubt"] is None
    assert RC.analyze_conditions(["weak"])[0]["doubt"] == "confirm"


def test_subtypes_of_one_disease_are_one_reading(judged):
    read = judged({"HC": row(HCM3, "hypertrophic cardiomyopathy 3", ["neurologic"], 0.9, others=[("MONDO:0008647", "hypertrophic cardiomyopathy 1", ["renal"], 0.89)])})
    link = read("HC")[2]
    assert [o["mondo"] for o in link["readings"]] == [HCM] and not link["ambiguous"]
