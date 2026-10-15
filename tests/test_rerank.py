"""Learned reranker of the nearest MONDO concepts (ml/mondo_index.py, index v4; trained by ml/rerank_train.py)."""
import pathlib, sys

import numpy as np
import pytest

pytest.importorskip("torch")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ml"))
import mondo_index as MI


@pytest.fixture
def tiny(monkeypatch):
    ids = ["M:1", "M:1", "M:2", "M:3"]
    idx = dict(_ids=ids, ids=np.array(ids), names=np.array(["asthma", "asthma", "atrial septal defect", "autism"]),
               axes=np.array([[0, 0, 0, 1] + [0] * 9, [0, 0, 0, 1] + [0] * 9, [0, 0, 1, 0] + [0] * 9, [0] * 6 + [1] + [0] * 6], np.float32),
               abbr_keys=np.array(["asd"]), abbr_vals=np.array(["M:2;M:3"]))
    monkeypatch.setattr(MI, "_IDX", idx)
    return idx


def test_candidates_are_concepts_with_their_best_string_and_count(tiny):
    c = MI.concept_candidates([0, 1, 2, 3], [0.9, 0.8, 0.7, 0.6])
    assert c == [("M:1", 0.9, 2), ("M:2", 0.7, 1), ("M:3", 0.6, 1)]


def test_features_have_one_row_per_candidate_and_mark_abbreviation_hits(tiny):
    X = MI.rr_features("asd", MI.concept_candidates([0, 2, 3], [0.8, 0.79, 0.7]))
    assert X.shape[0] == 3 and X[0, 10] == 0 and X[1, 10] == 1 and X[2, 10] == 1   # abbr_hit column


def test_scores_reorder_and_readings_follow_the_decision(tiny):
    c = MI.concept_candidates([0, 2], [0.8, 0.79]); n = MI.rr_features("asd", c).shape[1]
    w = np.zeros(n, np.float32); w[10] = 5.0                                         # a reranker that trusts the abbreviation table
    tiny.update(rr_w=w, rr_b=np.float32(0), rr_mu=np.zeros(n, np.float32), rr_sd=np.ones(n, np.float32), rr_threshold=np.float32(1))
    z = MI.rerank_scores("asd", c)
    assert z[1] > z[0]
    assert MI.readings("asd", [("M:2", 0.79), ("M:1", 0.8)], accepted=True)[0]["mondo"] == "M:2"
    assert all(r["why"] != "closest name" for r in MI.readings("asd", [("M:2", 0.79)], accepted=False))
