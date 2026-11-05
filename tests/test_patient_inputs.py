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