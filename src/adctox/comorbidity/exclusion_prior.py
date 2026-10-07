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

# Two filters, because magnitude alone was serving noise.
#
# Magnitude. Below this the enrichment is not worth showing against the base rate every
# oncology protocol carries. Measured spread across mechanisms, per organ:
#
#   renal 4.0x   cardiovascular 4.8x   haematologic 4.9x   gastrointestinal 8.7x
#   metabolic 17.6x   pulmonary 19.3x   hepatic 19.6x   infectious/immune 21.3x
#   neurologic 32.3x   dermatologic 84.0x   ocular 109.3x
#
# An earlier version of this comment claimed cardiovascular and infectious/immune both
# vary "only 1.8x" and were therefore the boilerplate pair. Half right: the flat organs
# are renal, cardiovascular and haematologic at 4-5x, while infectious/immune is 21.3x,
# among the most variable. The LVEF-floor reasoning held; the hepatitis-B half did not.
MIN_INFORMATIVE_ODDS_RATIO = 2.0

# Significance. 66 (mechanism, organ) cells are inspected at once, so a large ratio on a
# mechanism with one agent is cheap. Three cells cleared the magnitude filter on noise:
# dna_alkyl/ocular at 13.57x with p = 0.11, protein_synth/infectious_immune at 5.23x with
# p = 0.026, protein_synth/pulmonary at 3.01x with p = 0.056. Each comes from a mechanism
# represented by a single drug, so the figure was one sponsor's habits presented as an
# expert prior -- the same shape as the fabricated Haldane ratios this project already had
# to withdraw. Benjamini-Hochberg over all cells removes exactly those three.
FDR_Q = 0.05


def _bh_critical_p(pvalues: list[float], q: float = FDR_Q) -> float:
    """Largest p that Benjamini-Hochberg rejects at `q`, or 0.0 if none.

    Applied across every cell rather than per mechanism: the question being asked is
    "which of these 66 figures is worth showing", which is one simultaneous inspection.
    """
    ps = sorted(p for p in pvalues if p is not None)
    if not ps:
        return 0.0
    n = len(ps)
    crit = 0.0
    for i, p in enumerate(ps, start=1):
        if p <= q * i / n:
            crit = p
    return crit


@lru_cache(maxsize=1)
def _load(path: Path = ARTIFACT) -> dict[str, dict[str, dict]]:
    if not Path(path).exists():
        return {}
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = doc.get("by_mechanism", [])
    crit = _bh_critical_p(
        [cell.get("p") for row in rows for cell in row["cells"]]
    )
    out: dict[str, dict[str, dict]] = {}
    for row in rows:
        out[row["mechanism"]] = {
            cell["organ"]: {
                "odds_ratio": cell["odds_ratio"],
                "rate": cell["rate"],
                "n_trials": cell["n"],
                "p": cell.get("p"),
                "fdr_significant": (
                    cell.get("p") is not None and cell["p"] <= crit
                ),
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
        # base rate, and showing it would imply information it does not carry.
        return None
    if not cell.get("fdr_significant"):
        # A large ratio that does not survive correction across the 66 cells is one
        # sponsor's protocol habits, not a prior about the chemistry.
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
        "p_value": cell.get("p"),
    }
