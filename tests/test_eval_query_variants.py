import os, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ml"))
import eval_query_variants as QV

CONCEPTS = {"c1": ["one", ["hepatic", "renal"], "label"], "c2": ["two", ["ocular"], "label"]}
ITEMS = [dict(id="c1", query="q1", category="lay"), dict(id="c1", query="q2", category="lay"), dict(id="c2", query="q3", category="lay")]
ROWS = [dict(organs=["hepatic", "renal"], ok=True), dict(organs=["hepatic"], ok=True), dict(organs=[], ok=False)]


def test_scores_by_type_with_hand_computed_macro():
    r = QV.score(ITEMS, ROWS, CONCEPTS, n_boot=50)["lay"]
    assert (r["n"], r["concepts"]) == (3, 2)
    # hepatic tp 2; renal tp 1 fn 1; ocular fn 1 -> F1 1.0, 2/3, 0
    assert r["macro_f1"] == pytest.approx((1 + 2 / 3 + 0) / 3)
    assert r["reject"] == pytest.approx(1 / 3) and r["exact"] == pytest.approx(1 / 3)
    assert "typo" not in QV.score(ITEMS, ROWS, CONCEPTS, n_boot=5)
