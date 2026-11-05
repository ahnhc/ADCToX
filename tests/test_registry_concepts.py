"""conf/registry_concepts.json (ml/registry_concepts.py): which registry condition a concept the organ judge links to stands for."""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
M = json.loads((ROOT / "conf/registry_concepts.json").read_text(encoding="utf-8"))
REG = [r["id"] for r in csv.DictReader((ROOT / "conf/comorbidity_registry.csv").open(encoding="utf-8"))]


def test_anchors_cover_the_registry_and_point_into_it():
    import registry_concepts as RCN
    assert set(M["anchors"]) == set(REG) == set(RCN.ANCHORS)
    assert M["anchors"] == RCN.ANCHORS, "rebuild: python -I ml/registry_concepts.py"
    assert set(M["concepts"].values()) <= set(REG)


def test_each_anchor_maps_to_its_own_condition():
    for rid, anchors in M["anchors"].items():
        for a in anchors:
            if not a.startswith("!"): assert M["concepts"][a.rstrip(">")] == rid, (rid, a)


def test_known_cases():
    C = M["concepts"]
    assert C.get("MONDO:0005147") != "diabetic_neuropathy"         # type 1 diabetes (the registry's old pin for diabetic neuropathy)
    assert C["MONDO:0001583"] == "diabetic_neuropathy"           # diabetic polyneuropathy: the nearer anchor, not peripheral neuropathy
    assert C["MONDO:0005009"] == "heart_failure"                 # congestive heart failure is heart failure, not reduced LVEF
    assert C["MONDO:0005011"] == "inflammatory_bowel_disease"    # Crohn disease
    assert "MONDO:0000705" not in C                              # C. difficile colitis is not IBD (MONDO files every colitis under it)
    assert "MONDO:0005388" not in C                              # primary biliary cholangitis is not cirrhosis
    assert C["HP:0001394"] == "cirrhosis" and C["MONDO:0005366"] == "hepatitis_b_chronic"
    assert C["MONDO:0004375"] == "dialysis" and C["HP:0003774"] == "ckd_stage_4_5" and C["MONDO:0005300"] == "ckd_stage_3"
    assert not any(v in ("reduced_lvef", "prior_anthracycline", "prior_hsct") for v in C.values())
