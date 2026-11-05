"""linking_models.gold_held on a fake ontology: ADCTOX_RELEASE_DEV_GOLD=1 frees the dev-split gold and its relatives, nothing of the test split."""
import json, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml"))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
pytest.importorskip("torch")                                   # research environment only (ml/ needs torch)


def named(split_of, split, n):
    return [g for g in (f"g{k}" for k in range(1000)) if split_of(g) == split][:n]


@pytest.fixture
def world(tmp_path, monkeypatch):
    import eval_linking as EL
    dev, dev_group = named(EL.split_of, "dev", 2); test, test_group = named(EL.split_of, "test", 2)
    (tmp_path / "raw").mkdir()
    Q = [dict(qid=dev, group=None), dict(qid=test, group=None), dict(qid="in_test_group", group=test_group), dict(qid="in_dev_group", group=dev_group), dict(qid="no_concept", group=None)]
    G = [dict(qid=dev, concepts=["D"]), dict(qid=test, concepts=["X"]), dict(qid="in_test_group", concepts=["GROUPED_TEST"]), dict(qid="in_dev_group", concepts=["GROUPED_DEV"]), dict(qid="no_concept", concepts=[])]
    (tmp_path / "raw" / "queries_v0.json").write_text(json.dumps(Q), encoding="utf-8")
    (tmp_path / "gold_v0.jsonl").write_text("".join(json.dumps(g) + "\n" for g in G), encoding="utf-8")
    monkeypatch.setattr(EL, "D", str(tmp_path) + "/")
    monkeypatch.delenv("ADCTOX_RELEASE_DEV_GOLD", raising=False)
    return dict(
        D=dict(parents=["D_PARENT"]), D_PARENT=dict(parents=[]), D_CHILD=dict(parents=["D"]),
        X=dict(parents=["X_PARENT"]), X_PARENT=dict(parents=[]), X_CHILD=dict(parents=["X"]),
        BOTH=dict(parents=["D", "X"]), GROUPED_TEST=dict(parents=[]), GROUPED_DEV=dict(parents=[]), OTHER=dict(parents=[]),
    )


def test_default_holds_every_gold_concept_and_its_relatives(world):
    import linking_models as LM
    assert LM.gold_held(world) == {"D", "D_PARENT", "D_CHILD", "X", "X_PARENT", "X_CHILD", "BOTH", "GROUPED_TEST", "GROUPED_DEV"}


@pytest.mark.parametrize("value", ["0", "", "true"])
def test_only_the_value_1_turns_the_knob_on(world, monkeypatch, value):
    import linking_models as LM
    expected = LM.gold_held(world)
    monkeypatch.setenv("ADCTOX_RELEASE_DEV_GOLD", value)
    assert LM.gold_held(world) == expected


def test_release_frees_the_dev_side_and_a_relative_of_both_stays_held(world, monkeypatch):
    import linking_models as LM
    monkeypatch.setenv("ADCTOX_RELEASE_DEV_GOLD", "1")
    assert LM.gold_held(world) == {"X", "X_PARENT", "X_CHILD", "BOTH", "GROUPED_TEST"}


def test_a_dev_gold_concept_that_is_a_relative_of_test_gold_stays_held(world, monkeypatch):
    import linking_models as LM
    monkeypatch.setenv("ADCTOX_RELEASE_DEV_GOLD", "1")
    world["D"]["parents"].append("X")
    assert "D" in LM.gold_held(world)
