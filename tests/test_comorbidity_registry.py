"""The comorbidity registry is validated at load, because getting it wrong is silent.

A misspelled organ axis fails in two contradictory directions at once and announces
neither. Measured on a deliberate typo before the guard existed:

  * `comorbidity_weights` iterates the fourteen real axes and never looks the misspelling
    up, so every weight stays at 1.0 and the patient's declared vulnerability becomes
    completely inert.
  * constraint C6 iterates the at-risk set and rejects every candidate design for having
    no evidence on an organ that does not exist.

So one typo either ignores the comorbidity or refuses to answer, and the output looks
ordinary either way. This is the same failure shape as the axis ontology's comma-splitting
bug, which silently emptied the pulmonary axis.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from adctox.schemas import comorbidity_registry
from adctox.taxonomy import default_taxonomy

CONF = Path(__file__).resolve().parents[1] / "conf"


def test_the_shipped_registry_loads_and_every_axis_is_real():
    known = set(default_taxonomy().axis_order)
    rows = comorbidity_registry()
    assert len(rows) >= 40
    for cid, row in rows.items():
        assert row["organ_axes"], cid
        assert not set(row["organ_axes"]) - known, cid
        assert 0.0 < row["severity"] <= 1.0, cid
        assert row["severity_basis"].strip(), cid


def test_multi_axis_conditions_survive_the_separator():
    """Four conditions carry two axes, separated by ';'. The separator is the thing most
    likely to be got wrong by a later editor, and splitting on the wrong character would
    leave an unparseable axis name rather than an error."""
    rows = comorbidity_registry()
    multi = {c: r["organ_axes"] for c, r in rows.items() if len(r["organ_axes"]) > 1}
    assert len(multi) >= 4, f"expected several multi-axis conditions, found {multi}"
    for cid, axes in multi.items():
        for a in axes:
            assert ";" not in a and "," not in a and "|" not in a, (cid, a)


def _write(tmp_path: Path, organ_axes: str, severity: str = "1.0",
           basis: str = "a stated reason") -> Path:
    src = (CONF / "comorbidity_registry.csv").read_text(encoding="utf-8")
    header = src.splitlines()[0]
    cols = next(csv.reader([header]))
    row = {c: "" for c in cols}
    row.update({"id": "probe", "label": "Probe", "organ_axes": organ_axes,
                "severity": severity, "severity_basis": basis})
    out = tmp_path / "comorbidity_registry.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerow(row)
    return out


@pytest.mark.parametrize(
    "kwargs, expect",
    [
        ({"organ_axes": "pulmonry"}, "not in the ontology"),       # the typo
        ({"organ_axes": ""}, "declares no organ axis"),
        ({"organ_axes": "pulmonary", "basis": "  "}, "no severity_basis"),
        ({"organ_axes": "pulmonary", "severity": "1.4"}, "outside (0, 1]"),
        ({"organ_axes": "pulmonary", "severity": "0"}, "outside (0, 1]"),
    ],
)
def test_bad_rows_raise_rather_than_load(tmp_path, monkeypatch, kwargs, expect):
    """Each of these was previously accepted and failed silently downstream."""
    import adctox.schemas as schemas

    path = _write(tmp_path, **kwargs)
    monkeypatch.setattr(schemas, "CONF", path.parent)
    schemas.comorbidity_registry.cache_clear()
    try:
        with pytest.raises(ValueError, match=expect.replace("(", r"\(").replace(")", r"\)")):
            schemas.comorbidity_registry()
    finally:
        schemas.comorbidity_registry.cache_clear()


def test_a_typo_would_otherwise_be_inert_and_rejecting_at_once():
    """Pins both halves of the silent failure, so the guard's justification is measured.

    If either half ever stops being true the guard may be reconsidered; while both hold,
    loading an unvalidated registry is indefensible.
    """
    from adctox.design.constraints import ConstraintEngine
    from adctox.design.enumerate import DesignSpace
    from adctox.design.search import comorbidity_weights

    axes = list(default_taxonomy().axis_order)
    weights = comorbidity_weights(axes, {"pulmonry": 1.0}, lam=2.0)
    assert set(weights.values()) == {1.0}, (
        "a misspelled axis no longer makes the condition inert; re-read the guard's "
        "rationale in schemas.comorbidity_registry"
    )

    design = DesignSpace().enumerate("ERBB2", tier=1)[0][0]
    res = ConstraintEngine().check(
        design, at_risk_axes={"pulmonry"}, evidence_arms={a: 50 for a in axes}, min_arms=3
    )
    assert not res.passed and res.binding == "C6_evidence_on_at_risk_axes", (
        "a misspelled at-risk axis no longer rejects every design; the other half of the "
        "silent failure has changed"
    )
