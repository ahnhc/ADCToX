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


def test_judge_link_beats_a_similar_registry_name():
    import recommend as RC
    reg = next(i for i, r in RC._reg.items() if r.get("mondo_id"))
    own = RC._reg[reg]["mondo_id"]
    judged = lambda mondo, axes: dict(judge=True, mondo=mondo, axes=axes)
    assert RC._judge_differs(judged("MONDO:9999999", ["renal"]), reg)          # another disease with organs: the judge stands
    assert not RC._judge_differs(judged(own, ["renal"]), reg)                  # the registry condition's own concept
    assert not RC._judge_differs(judged(None, []), reg)                        # not placed in MONDO: the registry name matches
    assert not RC._judge_differs(dict(mondo="MONDO:9999999", axes=["renal"]), reg)    # the older linker: unchanged
