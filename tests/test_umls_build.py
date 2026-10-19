"""ml/umls_build.py on a made-up five-concept UMLS sample (tests/fixtures/umls_mini): gold isolation and the licence filter."""
import json, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml"))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")


def test_umls_build(tmp_path):
    pytest.importorskip("torch")                               # research environment only (ml/ needs torch)
    import build_linking_pools as BLP
    if not os.path.exists(BLP.OBO): pytest.skip("mondo.obo not downloaded")
    import umls_build as U
    man = U.main(["--meta", os.path.join(ROOT, "tests/fixtures/umls_mini/META"), "--srl", "0,3", "--out", str(tmp_path) + "/"])
    pairs = [json.loads(l) for l in open(tmp_path / "pairs.jsonl", encoding="utf-8")]
    items = [json.loads(l) for l in open(tmp_path / "items.jsonl", encoding="utf-8")]
    texts = {p["b"] for p in pairs} | {p["a"] for p in pairs} | {i["text"] for i in items}
    assert man["dropped_held_link"] == 1                     # C0162316 links to iron deficiency anemia, a gold concept
    assert man["dropped_held_name"] == 1                     # C7777777 is unlinked but carries a gold concept's name
    assert "IDA" not in texts                                 # an evaluation question
    assert "Made up disorder suppressed" not in texts         # SUPPRESS O
    assert "Lateral femoral cutaneous neuropathy" not in texts   # SRL 9 (SNOMED CT) not asked for
    assert "Some anatomy" not in texts                        # not a disorder
    assert {i["mondo"] for i in items} == {"MONDO:0023757"} and man["korean_pairs"] == 1
