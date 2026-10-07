"""The evidence served with every ranking must agree with its own numbers.

These verdicts were hand-written strings and had drifted in both directions at once:
leave-one-agent-out was labelled "model loses to the baseline" when its interval includes
zero, and the dose-modification comparison was labelled "model beats the baseline" when
its interval also includes zero and the model card already said that comparison stopped
being favourable after the centering-bug fix. One prose verdict was too pessimistic, the
other too optimistic, and nothing tied either to the interval beside it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from adctox.api.main import _verdict  # noqa: E402


def test_verdict_follows_the_interval():
    assert _verdict(+0.05, [+0.01, +0.09]) == "model beats the baseline"
    assert _verdict(-0.05, [-0.09, -0.01]) == "model loses to the baseline"
    for ci in ([-0.01, +0.09], [-0.09, +0.01], [0.0, +0.09]):
        assert "includes zero" in _verdict(+0.01, ci), ci


def test_verdict_reports_absence_rather_than_guessing():
    for delta, ci in ((None, [0.1, 0.2]), (0.1, None), (0.1, []), (0.1, [None, 0.2])):
        assert _verdict(delta, ci) == "not computed"


def test_served_verdicts_match_their_own_intervals():
    """The end-to-end guard: no evaluation may claim a direction its interval denies."""
    from fastapi.testclient import TestClient

    from adctox.api.main import app

    doc = TestClient(app).get("/api/v1/ranking-evidence").json()
    assert doc["evaluations"], "no evaluations served"
    checked = 0
    for ev in doc["evaluations"]:
        ci = ev.get("delta_ci")
        if not ci or len(ci) != 2 or ci[0] is None:
            continue
        checked += 1
        lo, hi = ci
        v = ev["verdict"]
        if lo <= 0 <= hi:
            assert "includes zero" in v, (
                f"{ev['name']}: interval [{lo}, {hi}] spans zero but the verdict claims "
                f"a direction: {v!r}"
            )
        elif lo > 0:
            assert "beats" in v, f"{ev['name']}: {v!r} against [{lo}, {hi}]"
        else:
            assert "loses" in v, f"{ev['name']}: {v!r} against [{lo}, {hi}]"
    assert checked >= 3, f"only {checked} evaluations carried an interval to check"


def test_every_measured_evaluation_is_served():
    """A favourable-looking ranking must not be served with only the kind evaluations.

    The anticipatory label-change test and the label-rule necessity measurement are both
    unfavourable, and both were missing from this payload after being computed.
    """
    from fastapi.testclient import TestClient

    from adctox.api.main import app

    names = " ".join(
        e["name"] for e in TestClient(app).get("/api/v1/ranking-evidence").json()["evaluations"]
    )
    for expected in ("within-arm axis ranking", "across-agent", "dose-modification"):
        assert expected in names, f"{expected} missing from the served evidence"
