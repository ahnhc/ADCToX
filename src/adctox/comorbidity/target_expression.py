"""Target-antigen abundance in an at-risk organ, served as a flag.

The mechanism: on-target off-tumour toxicity. The antibody binds healthy tissue that
expresses the target, the payload is released there, and the organ is damaged. If the
patient is already compromised in that organ, that matters.

Why this is a flag and not a constraint, measured rather than assumed:

  * Across 14 approved ADCs and their labels' dose-modification tables, target expression
    does NOT predict which organs a label warns about -- AUROC 0.521 from GTEx and 0.576
    from Tabula Sapiens, and controlling for payload mechanism does not rescue it. That
    agrees with the preclinical literature the project cites: toxicity is largely
    antigen-independent and target tissue expression correlates poorly with dose-limiting
    toxicity (PMID 38692647).
  * But it does recover the specific on-target cases: all five textbook pairs land in the
    target's top expression quintile, against a chance expectation of one in five.

So expression says *which organ a target could damage*, not *how toxic a drug is*. Raising
a band and naming a driver is the action that claim supports. Rejecting candidates is not:
a rejection rule was prototyped and removed 87% of candidates whenever it fired while
never changing the recommendation, because the two non-permeable payloads it spares were
already the top-ranked ones.

This layer is deliberately target-level, so it does not discriminate between candidates
sharing a target. That is honest about what it knows. The payload-level question -- does a
bystander-permeable payload extend the damage past the antigen-positive cells -- is
reported alongside, because it is the part that varies by candidate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ARTIFACT = Path(__file__).resolve().parents[3] / "artifacts" / "target_expression.json"


@dataclass(frozen=True)
class ExpressionFlag:
    target: str
    axis: str
    percentile: float
    tissue: str | None
    cell_types: tuple[str, ...]
    permeable_payload: bool

    def as_driver(self) -> dict:
        extra = (
            " The payload is bystander-permeable, so damage is not confined to "
            "antigen-positive cells."
            if self.permeable_payload
            else " The payload is not bystander-permeable, so damage is confined to "
            "cells that carry the target."
        )
        cells = (
            f" Highest-expressing cell types: {', '.join(self.cell_types)}."
            if self.cell_types else ""
        )
        # At percentile 1.0 the "top N%" phrasing degenerates to "top 0%", and a bare
        # ordinal suffix produces "83th". Both read as carelessness in output a clinician
        # is meant to weigh.
        if self.percentile >= 1.0:
            factor = f"{self.target} is most abundant in this organ, of those measured"
        else:
            factor = (
                f"{self.target} is in the top "
                f"{100 * (1 - self.percentile):.0f}% of its own organ profile here"
            )
        return {
            "factor": factor,
            "detail": (
                f"{self.target} expression in {self.axis} sits at percentile "
                f"{100 * self.percentile:.0f} across the organs this target "
                f"is measured in"
                + (f", highest in {self.tissue}" if self.tissue else "")
                + f".{cells}{extra} This is the on-target off-tumour mechanism: the "
                "antibody binds healthy tissue carrying the target. It is a flag, not a "
                "prediction -- across 14 approved ADCs expression does not predict which "
                "organs their labels warn about (AUROC 0.52-0.58), but it does recover "
                "all five textbook on-target cases."
            ),
            "source": "target_expression",
            "contribution": None,
            "percentile": round(self.percentile, 3),
        }


@lru_cache(maxsize=1)
def _load(path: Path = ARTIFACT) -> dict:
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluable(target: str) -> bool:
    """Whether this target has an expression profile at all.

    A target absent from the snapshot must report "not evaluated" rather than pass
    silently: constraint C3 spent the project's whole life declared and never evaluated,
    and nothing said so.
    """
    return target.upper() in (_load().get("targets") or {})


def applicable(
    target: str,
    at_risk_axes: set[str],
    permeable_payload: bool,
    enabled: bool = True,
) -> dict[str, ExpressionFlag]:
    """Flags for the at-risk axes where this target is abundant, keyed by axis."""
    doc = _load()
    if not enabled or not doc:
        return {}
    spec = (doc.get("targets") or {}).get(target.upper())
    if spec is None:
        return {}
    cut = float(doc["abundant_percentile"])
    out: dict[str, ExpressionFlag] = {}
    for axis in sorted(at_risk_axes):
        pct = spec["percentile"].get(axis)
        if pct is None or pct < cut:
            continue
        tissue = None
        for src in ("gtex", "tabula_sapiens"):
            cell = spec["values"].get(src, {}).get(axis)
            if cell:
                tissue = cell[1]
                break
        cells = tuple(
            c[2]
            for src in ("tabula_sapiens",)
            for c in (spec.get("cell_evidence", {}).get(src, {}).get(axis) or [])
        )[:2]
        out[axis] = ExpressionFlag(
            target=target.upper(), axis=axis, percentile=float(pct),
            tissue=tissue, cell_types=cells, permeable_payload=permeable_payload,
        )
    return out
