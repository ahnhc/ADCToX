"""The rejected dose-modification measure, and why it was rejected.

`axis_severity` has no call sites. It is kept because its failure is the reason
`axis_concern` is built the way it is, and that reason was asserted in a docstring --
"approved labels tell you to discontinue for the severe grade of nearly every reaction, so
almost every axis collapses to the top of the scale" -- without anything measuring it.
An untested claim in a comment is how this project got its worst bugs, so the claim is
measured here instead. If it ever stops being true, `axis_severity` becomes the better
measure and these tests say so by failing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from adctox.validation.dose_modification import (
    axis_concern,
    axis_severity,
    parse_tables,
)

LABELS = Path("/data/hyeongchanahn/adctox/raw/openfda_label")
CONF = Path(__file__).resolve().parents[1] / "conf"


def _entries():
    if not LABELS.exists():
        pytest.skip("label corpus not present")
    dates = sorted(p for p in LABELS.iterdir() if p.is_dir())
    if not dates:
        pytest.skip("no dated label snapshot")
    snapshot = dates[-1]
    agents = yaml.safe_load((CONF / "adc_registry.yaml").read_text(encoding="utf-8"))
    out = []
    for agent in agents["agents"]:
        path = snapshot / f"{agent}.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        tables = doc.get("dosage_and_administration_table") or []
        out.extend(parse_tables(agent, tables))
    if not out:
        pytest.skip("no dose-modification entries parsed")
    return out


def test_severity_collapses_and_concern_does_not():
    """The measurement behind the design choice.

    Severity takes the strongest action per axis on a 1-4 scale. If the docstring is
    right, nearly every axis lands at 4 and the measure cannot order organs.
    """
    entries = _entries()
    sev = axis_severity(entries)
    con = axis_concern(entries)
    assert sev and con

    at_ceiling = sum(1 for v in sev.values() if v == max(sev.values()))
    frac = at_ceiling / len(sev)
    assert frac > 0.6, (
        f"only {100 * frac:.0f}% of axes sit at the severity ceiling, so severity is no "
        "longer the poor discriminator the docstring claims. Re-examine whether "
        "axis_concern is still the right measure before changing this bound."
    )
    # The graded measure has to actually distinguish organs, or it is no better.
    assert len(set(round(v, 2) for v in con.values())) > len(set(sev.values())), (
        "axis_concern resolves no more distinct levels than axis_severity; the extra "
        "complexity would be buying nothing"
    )


def test_concern_is_ordinal_and_bounded():
    """Score = action (1-4) plus an earliness bonus, so it must stay inside that range."""
    con = axis_concern(_entries())
    for axis, v in con.items():
        assert 1.0 <= v <= 5.0, f"{axis} scored {v}, outside the documented 1-4 + bonus"


def test_severity_is_still_reachable_from_the_tests_that_justify_it():
    """A guard against quietly deleting the rejected measure.

    If someone removes `axis_severity` as dead code, this file stops importing and the
    rationale for `axis_concern` loses its evidence. Deleting it is fine -- but then the
    docstring claim in dose_modification.py has to go too.
    """
    assert callable(axis_severity)
