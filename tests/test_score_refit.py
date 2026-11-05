"""ml/score_refit.py: the declared first-experiment predicate, and its refusal to read the test split."""
import os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ml"))
import score_refit as S


@pytest.mark.parametrize("gain,rejections,known_drop,expected", [
    (0.03, 7, 0.01, "PASS"),
    (0.08, 0, -0.02, "PASS"),
    (0.0299, 7, 0.0, "INCONCLUSIVE"),
    (0.03, 7.34, 0.0, "INCONCLUSIVE"),
    (0.05, 3, 0.011, "INCONCLUSIVE"),
    (0.01, 15, 0.5, "INCONCLUSIVE"),
    (0.0099, 0, 0.0, "FAIL"),
    (-0.05, 0, 0.0, "FAIL"),
])
def test_verdict(gain, rejections, known_drop, expected):
    assert S.verdict(gain, rejections, known_drop) == expected


@pytest.mark.parametrize("argv", [
    ["--split", "test", "--baseline", "b7", "--arm", "A", "a7"],
    ["--test", "--baseline", "b7", "--arm", "A", "a7"],
    ["--baseline", "ml/results/final_test.json", "--arm", "A", "a7"],
    ["--baseline", "b7", "--arm", "A", "final_test/a7"],
])
def test_refuses_the_test_split_before_reading_anything(argv):
    with pytest.raises(SystemExit) as e: S.main(argv)
    assert "dev only" in str(e.value)


@pytest.mark.parametrize("base,arm", [(["x/b7", "x/b8"], ["x/a7"]), (["x/b"], ["x/a7"])])
def test_runs_are_paired_by_seed(base, arm):
    with pytest.raises(SystemExit): S.paired(base, arm)
