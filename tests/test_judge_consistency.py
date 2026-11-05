"""models 0.7+: the app reads a disease the way the from-scratch judge does (ml/scratch_runtime.py), wherever it reaches it."""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ml"))
import scratch_runtime as SR


def _folder(tmp_path, monkeypatch):
    (tmp_path / "judge.json").write_text("{}")
    (tmp_path / "concepts.json").write_text(json.dumps({
        "MONDO:1": ["type 1 diabetes mellitus", ["metabolic_endocrine", "infectious_immune"], "record"],
        "MONDO:2": ["type 2 diabetes mellitus", ["metabolic_endocrine"], "label"],
        "MONDO:3": ["no organs", [], ""], "HP:1": ["a phenotype", [], ""]}))
    monkeypatch.setattr(SR, "folder", lambda: str(tmp_path)); SR._ORG.clear()


def test_list_organs_are_the_judges(tmp_path, monkeypatch):
    _folder(tmp_path, monkeypatch)
    assert SR.concept_organs() == {"MONDO:1": ["metabolic_endocrine", "infectious_immune"], "MONDO:2": ["metabolic_endocrine"]}
    assert (SR.concept_via("MONDO:1"), SR.concept_via("MONDO:2"), SR.concept_via("MONDO:3")) == ("record", "label", None)
    monkeypatch.setenv("ADC_SCRATCH_JUDGE", "0")
    assert SR.concept_organs() == {} and SR.concept_via("MONDO:1") is None


def test_the_judges_concept_names_the_registry_condition(monkeypatch):
    import recommend as RC
    link = lambda concept, name: dict(judge=True, mondo=concept, concept=concept, concept_name=name, name=name, axes=["metabolic_endocrine"], sim=0.95, gate=True)
    links = {"type 2 diabetes": link("MONDO:0005148", "type 2 diabetes mellitus"), "type 1 diabetes": link("MONDO:0005147", "type 1 diabetes mellitus")}
    monkeypatch.setattr(RC, "_free_info", lambda free, progress=None: [links[c] for c in free])
    s, _, ids, notes, _ = RC.resolve(["type 2 diabetes"])
    assert ids == {"type_2_diabetes"} and s[RC.AXES.index("metabolic_endocrine")] == float(RC._reg["type_2_diabetes"]["severity"])
    _, _, ids, notes, _ = RC.resolve(["type 1 diabetes"])            # a similar name is not the registry condition
    assert ids == set() and "MONDO 'type 1 diabetes mellitus'" in notes[0][1]
