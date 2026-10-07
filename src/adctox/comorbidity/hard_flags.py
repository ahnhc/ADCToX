"""Label-derived overrides that the model's arithmetic must not be able to outvote.

A small number of chemistry-comorbidity pairs are addressed directly in approved
labelling. Where a regulator has answered the question, a fitted score should not be able
to overrule it -- particularly here, where that score does not beat a base-rate baseline.

The companion requirement is provenance. A reviewer will ask whether a red pulmonary axis
on a deruxtecan design is a prediction or something we wrote down, and if the output cannot
answer that, the model's own predictions lose credibility by association. So every flag
carries its verbatim quotation and the label section it came from, is reported with
`source: "rule"`, and the case-study evaluation can switch the layer off entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

CONF = Path(__file__).resolve().parents[3] / "conf" / "hard_flags.yaml"


@dataclass(frozen=True)
class HardFlag:
    id: str
    mechanisms: frozenset[str]
    payloads: frozenset[str]
    comorbidities: frozenset[str]
    axis: str
    tier: str
    source_label: str
    source_section: str
    quote: str
    note: str

    def as_driver(self) -> dict:
        """The flag as a driver entry, marked so it cannot be mistaken for a fitted term."""
        return {
            "factor": f"label rule: {self.id}",
            "detail": (
                f"{self.source_label} {self.source_section}: "
                f"{' '.join(self.quote.split())}"
            ),
            "source": "rule",
            # A rule has no logit contribution; it overrides the band instead. Reporting a
            # number here would imply it was fitted alongside the model terms.
            "contribution": None,
            "tier": self.tier,
        }


@lru_cache(maxsize=1)
def load_flags(path: Path = CONF) -> tuple[tuple[HardFlag, ...], tuple[str, ...]]:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    flags = tuple(
        HardFlag(
            id=f["id"],
            mechanisms=frozenset(f.get("mechanisms") or []),
            payloads=frozenset(f.get("payloads") or []),
            comorbidities=frozenset(f.get("comorbidities") or []),
            axis=f["axis"], tier=f["tier"],
            source_label=f["source_label"], source_section=f["source_section"],
            quote=f["quote"], note=f.get("note", ""),
        )
        for f in doc["flags"]
    )
    return flags, tuple(doc["tier_order"])


def applicable(
    mechanism: str,
    payload: str,
    condition_ids: set[str],
    enabled: bool = True,
) -> dict[str, list[HardFlag]]:
    """Flags that fire for this chemistry and these conditions, keyed by organ axis.

    `enabled=False` switches the layer off, which the case-study evaluation uses: a flag
    that hardcodes "prior ILD plus a deruxtecan payload is high risk" would make the
    deruxtecan case study pass without the model contributing anything, and a reviewer
    would be right to discount the result.
    """
    if not enabled:
        return {}
    flags, _ = load_flags()
    out: dict[str, list[HardFlag]] = {}
    for f in flags:
        if f.mechanisms and mechanism not in f.mechanisms:
            continue
        if f.payloads and payload not in f.payloads:
            continue
        if not (f.comorbidities & condition_ids):
            continue
        out.setdefault(f.axis, []).append(f)
    return out


def override_band(model_band: str, flags: list[HardFlag]) -> str:
    """Raise a band to match the strongest applicable flag, never lower it.

    Including when the model reports `no_evidence`: a label statement is evidence, and an
    organ a regulator warns about must not render as unstudied.
    """
    if not flags:
        return model_band
    _, tier_order = load_flags()
    strongest = min(flags, key=lambda f: tier_order.index(f.tier))
    mapped = {"avoid": "high", "monitor": "moderate"}[strongest.tier]
    severity = ["no_evidence", "low", "moderate", "high"]
    if model_band not in severity:
        return mapped
    return mapped if severity.index(mapped) > severity.index(model_band) else model_band
