"""Serve the measured exclusion-criteria enrichment as a per-(mechanism, axis) prior.

What it is: across 1,281 ADC trials against 2,481 oncology controls, how much more often
a protocol for this payload mechanism excludes patients with disease in a given organ than
an oncology protocol does. A sponsor writes those exclusions before any outcome is known,
having read the preclinical and early-phase data, so they encode an expert prior about
which organ the drug threatens.

What it is not: a prediction. For almost every agent the warning this recovers was already
in the label at approval, so agreement with it is consistency rather than anticipation.
And it is reported separately from the outcome model rather than combined with it, because
the two are negatively coupled by construction -- excluding ILD patients suppresses
observed ILD, so one measures hazard and the other residual risk after protective
selection. Pooling them would have the two cancel.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ARTIFACT = (
    Path(__file__).resolve().parents[3] / "artifacts" / "exclusion_enrichment_exclusion.json"
)

# Below this the enrichment is indistinguishable from the boilerplate every oncology
# protocol carries. Measured: cardiovascular and infectious/immune vary only 1.8x across
# mechanisms because every protocol has an LVEF floor and a hepatitis-B exclusion, while
# ocular varies 109x.
MIN_INFORMATIVE_ODDS_RATIO = 2.0


@lru_cache(maxsize=1)
def _load(path: Path = ARTIFACT) -> dict[str, dict[str, dict]]:
    if not Path(path).exists():
        return {}
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict[str, dict]] = {}
    for row in doc.get("by_mechanism", []):
        out[row["mechanism"]] = {
            cell["organ"]: {
                "odds_ratio": cell["odds_ratio"],
                "rate": cell["rate"],
                "n_trials": cell["n"],
                "p": cell.get("p"),
            }
            for cell in row["cells"]
        }
    return out


def driver(mechanism: str, axis: str) -> dict | None:
    """The enrichment for one (mechanism, axis) as a driver, or None if uninformative."""
    cell = _load().get(mechanism, {}).get(axis)
    if cell is None:
        return None
    ratio = float(cell["odds_ratio"])
    if ratio < MIN_INFORMATIVE_ODDS_RATIO:
        # Reported as nothing rather than as a weak signal: below this the figure is the
        # boilerplate rate, and showing it would imply information it does not carry.
        return None
    return {
        "factor": f"trial protocols exclude this organ {ratio:.1f}x more often",
        "detail": (
            f"across {cell['n_trials']} {mechanism} trials, {100 * cell['rate']:.0f}% "
            f"exclude patients with disease here, against the oncology base rate. "
            "Sponsors write exclusions before outcomes are known, so this is an expert "
            "prior about which organ the chemistry threatens -- not a prediction, and not "
            "pooled with the outcome model, which it is negatively coupled with."
        ),
        "source": "exclusion_head",
        "contribution": None,
        "odds_ratio": round(ratio, 2),
    }
