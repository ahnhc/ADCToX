"""Extract per-organ concern flags from clinical-trial eligibility text.

This is the auxiliary supervision signal that the forward model's outcome head cannot
provide: which organ a sponsor was already worried about, stated before any outcome
existed.

Critical modelling note, and the reason this never shares a head with the outcome model:
exclusions and outcomes are **negatively coupled by design**. Excluding patients with
interstitial lung disease suppresses the observed ILD rate. Measured instance: T-DXd's
exclusion signal for the pulmonary axis is strongly enriched while its observed
respiratory residual is neutral. Exclusion labels measure *hazard*; outcome labels
measure *residual risk after protective selection*. Pooling them would have the two
signals cancel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

RULES_YAML = (
    Path(__file__).resolve().parents[3] / "conf" / "ontology" / "organ_concern_rules.yaml"
)


@dataclass(frozen=True)
class _Pattern:
    organ: str
    polarity: str
    regex: re.Pattern[str]
    source: str


class OrganConcernExtractor:
    def __init__(self, rules_yaml: Path = RULES_YAML) -> None:
        doc = yaml.safe_load(rules_yaml.read_text(encoding="utf-8"))
        self.organs: list[str] = list(doc["organs"])
        self._unescape = tuple((doc.get("preprocess") or {}).get("unescape") or [])
        self._patterns: list[_Pattern] = []
        for organ, spec in doc["organs"].items():
            for pat in spec["patterns"]:
                self._patterns.append(
                    _Pattern(
                        organ=organ,
                        polarity=pat["polarity"],
                        regex=re.compile(pat["re"], re.IGNORECASE),
                        source=pat["re"],
                    )
                )

    def preprocess(self, text: str) -> str:
        """Undo ClinicalTrials.gov's markup escaping, which otherwise hides operators."""
        for esc in self._unescape:
            text = text.replace(esc, esc[-1])
        return re.sub(r"\s+", " ", text)

    def extract(self, text: str | None) -> dict[str, dict]:
        """Per-organ flags with the polarities and patterns that fired.

        Returns only organs with at least one hit, so an absent key means "no mention"
        rather than "mentioned and judged fine".
        """
        if not text:
            return {}
        norm = self.preprocess(text)
        out: dict[str, dict] = {}
        for pat in self._patterns:
            if pat.regex.search(norm):
                entry = out.setdefault(
                    pat.organ, {"polarities": set(), "patterns": [], "n_hits": 0}
                )
                entry["polarities"].add(pat.polarity)
                entry["patterns"].append(pat.source)
                entry["n_hits"] += 1
        for entry in out.values():
            entry["polarities"] = sorted(entry["polarities"])
        return out

    def flags(self, text: str | None) -> dict[str, bool]:
        """Flat organ -> bool over every known organ, suitable for a design matrix."""
        hit = self.extract(text)
        return {organ: organ in hit for organ in self.organs}

    def flags_by_polarity(self, text: str | None, polarity: str) -> dict[str, bool]:
        """Flags restricted to one polarity, so inclusion floors and explicit exclusions
        can be analysed apart."""
        hit = self.extract(text)
        return {
            organ: (organ in hit and polarity in hit[organ]["polarities"])
            for organ in self.organs
        }
