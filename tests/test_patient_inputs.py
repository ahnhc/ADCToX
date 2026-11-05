"""What a typed or picked patient input turns into: the registry condition behind it, the lab value it means, the verdict it gets."""
import pathlib, sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
import form
import recommend as RC


def row_of(rows, adc): return next(r for r in rows if r["adc"] == adc)


@pytest.mark.parametrize("typed", ["bleomycin", "Bleomycin", "블레오마이신", "concomitant bleomycin", "Concomitant  Bleomycin", "concomitant_bleomycin"])
def test_typed_bleomycin_contraindicates_brentuximab(typed):
    rows, _, notes, _ = RC.recommend([typed])
    row = row_of(rows, "brentuximab-vedotin")
    assert row["verdict"].worst_known == RC.RS.TIER["contraindicated"] and row["restriction"].startswith("Contraindicated")
    assert notes == [(typed, RC.CONTEXT["concomitant_bleomycin"])] and RC.unresolved([typed]) == []
    assert RC.analyze_conditions([typed]) == [] and RC.ambiguous_conditions([typed]) == []


def test_the_bleomycin_suggestion_reads_back_as_the_rule_condition():
    import suggest as SG
    for typed in ("bleomycin", "블레오마이신"):
        kind, value, label, *_ = SG.names(RC, typed)[0]
        assert kind == "text" and "bleomycin" in label.lower()
        _, free, _ = form.Form._split(None, [(kind, value, label, "", [])])
        assert RC.resolve(form.split_free(free))[2] == {"concomitant_bleomycin"}


def _no_link(monkeypatch):
    monkeypatch.setattr(RC, "_free_info", lambda free, progress=None: [dict(mondo=None, name="", sim=0.0, axes=[], gate=None, readings=[], ambiguous=False) for _ in free])


def _picked(monkeypatch, text, concept, name, organs):
    _no_link(monkeypatch)
    monkeypatch.setattr(RC, "_chosen", lambda mondo: (name, organs))
    monkeypatch.setitem(RC.CHOICE, text, concept)


def _typed(monkeypatch, concept, name, organs):
    link = dict(mondo=concept, name=name, sim=1.0, axes=organs, gate=True, valid=True, readings=[], ambiguous=False, judge=True, concept=concept, concept_name=name)
    monkeypatch.setattr(RC, "_free_info", lambda free, progress=None: [dict(link) for _ in free])


@pytest.mark.parametrize("concept, name, organs, registry, adc, domain, category", [
    ("MONDO:0005252", "heart failure", ["cardiovascular"], "heart_failure", "trastuzumab-deruxtecan", "cardiac", "insufficient_data"),
    ("HP:0001657", "prolonged QT interval", ["cardiovascular"], "qt_prolongation", "inotuzumab-ozogamicin", "qt", "monitor"),
    ("MONDO:0019514", "hepatic veno-occlusive disease", ["hepatic"], "hepatic_vod_history", "gemtuzumab-ozogamicin", "hepatic", "monitor"),
])
def test_a_picked_reading_counts_like_the_same_concept_typed(monkeypatch, concept, name, organs, registry, adc, domain, category):
    _picked(monkeypatch, "CHF", concept, name, organs)
    s, _, ids, _, pc = RC.resolve(["CHF"])
    assert ids == {registry}
    verdict = row_of(RC.recommend(["CHF"])[0], adc)["verdict"]
    assert any(c == category and r["domain"] == domain and registry in r["when"].get("condition", []) for c, r in verdict.known)
    picked = s.tolist(), pc
    monkeypatch.delitem(RC.CHOICE, "CHF")
    _typed(monkeypatch, concept, name, organs)
    s, _, ids, _, pc = RC.resolve(["CHF"])
    assert ids == {registry} and (s.tolist(), pc) == picked


def test_a_picked_reading_outside_the_registry_keeps_the_fixed_severity(monkeypatch):
    _picked(monkeypatch, "asthma", "MONDO:0004979", "asthma", ["pulmonary"])
    s, _, ids, _, pc = RC.resolve(["asthma"])
    assert ids == set() and pc == [("asthma", {"pulmonary"}, RC.MONDO_SEVERITY)]

def test_every_rule_threshold_is_reached_when_the_value_is_not_entered():
    import numbers
    RS = RC.RS; rules = RS.load_rules(); organ = {"renal": "renal", "hepatic": "hepatic", "blood": "haematologic", "cardiac": "cardiovascular", "metabolic": "metabolic_endocrine"}
    for rule in rules:
        if rule["domain"] not in organ or not any(isinstance(v, numbers.Number) and not isinstance(v, bool) for v in rule["when"].values()): continue
        verdict = RS.judge(RS.Patient(organs={organ[rule["domain"]]}), [rule["adc"]], rules)[rule["adc"]]
        assert any(r is rule for _, r in verdict.possible), rule


def test_belantamab_platelets_not_entered_may_be_avoid():
    rules = RC.RS.load_rules(); adc = "belantamab-mafodotin"
    open_ = RC.RS.judge(RC.RS.Patient(organs={"haematologic"}), [adc], rules)[adc]
    assert RC.RS.summary(open_) == "Avoid? (blood 2.3)" and open_.inputs == ["Platelets"]
    assert RC.RS.summary(RC.RS.judge(RC.RS.Patient(organs={"haematologic"}, platelets=20), [adc], rules)[adc]) == "Avoid (blood 2.3)"
    assert RC.RS.summary(RC.RS.judge(RC.RS.Patient(organs={"haematologic"}, platelets=25), [adc], rules)[adc]) == "-"

@pytest.mark.parametrize("typed", ["ESRD", "ESKD", "hemodialysis", "Haemodialysis", "peritoneal dialysis", "dialysis", "투석", "혈액투석", "복막투석"])
def test_typed_esrd_or_dialysis_counts_as_on_dialysis(typed):
    assert RC.resolve([typed])[2] == {"dialysis"} and RC.unresolved([typed]) == []
    verdict = row_of(RC.recommend([typed], None, {"egfr": 20})[0], "inotuzumab-ozogamicin")["verdict"]
    assert [c for c, r in verdict.known if r["domain"] == "renal"] == ["insufficient_data"]


@pytest.mark.parametrize("concept, name, organs", [("MONDO:0004375", "end stage renal failure", ["renal"]), ("MONDO:0975708", "dialysis disequilibrium syndrome", ["neurologic", "renal"])])
def test_the_esrd_and_dialysis_concepts_stand_for_dialysis_linked_or_picked(monkeypatch, concept, name, organs):
    _typed(monkeypatch, concept, name, organs)
    assert RC.resolve(["kidneys gone"])[2] == {"dialysis"}
    verdict = row_of(RC.recommend(["kidneys gone"], None, {"egfr": 20})[0], "inotuzumab-ozogamicin")["verdict"]
    assert [c for c, r in verdict.known if r["domain"] == "renal"] == ["insufficient_data"]
    _picked(monkeypatch, "kidneys gone", concept, name, organs)
    assert RC.resolve(["kidneys gone"])[2] == {"dialysis"}


def test_ckd_stage_5_is_not_read_as_dialysis(monkeypatch):
    _typed(monkeypatch, "HP:0003774", "Stage 5 chronic kidney disease", ["renal"])
    assert RC.resolve(["stage 5"])[2] == {"ckd_stage_4_5"}
