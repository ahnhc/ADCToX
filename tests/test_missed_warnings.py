import os, sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ml"))
import missed_warnings as MW

EVIDENCE = {"a": (2, 1), "b": (0, 3), "c": (1, 0), "d": (0, 0)}
GOLD = [["a", "b"], ["a", "c"], ["c", "d"], ["b"]]
PRED = [["a"], [], ["c", "d"], ["b", "c"]]


def test_hand_computed_numbers():
    r = MW.missed_warnings(PRED, GOLD, EVIDENCE)
    assert (r["boxed_links"], r["boxed_missed"], r["boxed_miss_rate"]) == (6, 3, 0.5)
    assert (r["wp_links"], r["wp_missed"], r["wp_miss_rate"]) == (8, 4, 0.5)
    assert r["questions_missed_boxed"] == 1
    assert r["silent_partial"] == 1
    assert r["organs_warned"] == 3
    assert r["macro_f1_warned"] == pytest.approx(11 / 18)


def test_no_gold_warning_gives_no_rate():
    r = MW.missed_warnings([[]], [["d"]], EVIDENCE)
    assert r["boxed_miss_rate"] is None and r["wp_miss_rate"] is None and r["macro_f1_warned"] is None


def test_warning_counts_read_the_label_evidence():
    c = MW.warning_counts()
    assert c["musculoskeletal"] == (0, 0) and c["otologic"] == (0, 0)
    assert sum(b for b, _ in c.values()) == 13
