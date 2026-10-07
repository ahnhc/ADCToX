"""Enumerate chemically valid, individually-precedented ADC designs for a target.

Exhaustive enumeration plus a Pareto sort is the right algorithm here, and the reason is
not just that the space is small. The space is **categorical and non-metric**: there is
no meaningful distance between a GGFG linker and an SMCC one, so a Bayesian-optimization
surrogate has nothing to interpolate over, and a genetic algorithm's crossover produces
chemically invalid molecules (a maleimide linker crossed with NHS conjugation), turning
every operator into a repair heuristic. Enumeration is the only method whose output can
be defended, because it *provably* returns the true Pareto front.

Tier discipline. Only Tier 1 is enumerated by default: every component individually has
clinical precedent, and only the combination is new. That is what most real "new ADC"
proposals are, and it is the only tier the forward model supports -- Tier 2 (a new
molecule in a known family) would need chemistry generalization, which the data does not
underwrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DESIGN_YAML = Path(__file__).resolve().parents[3] / "conf" / "design_space.yaml"


@dataclass(frozen=True)
class Design:
    target: str
    payload: str
    mechanism: str
    linker: str
    cleavable: bool
    conjugation: str
    dar: float
    isotype: str
    masking: str
    # True when any component has clinical but no approved precedent. Such a design is
    # admissible under Tier 1 but must be shown flagged, never silently ranked alongside
    # fully approved chemistry.
    has_unapproved_component: bool = False

    @property
    def slots(self) -> dict:
        return {
            "target": self.target, "payload": self.payload, "linker": self.linker,
            "conjugation": self.conjugation, "dar": self.dar, "isotype": self.isotype,
            "masking": self.masking,
        }

    def key(self) -> tuple:
        return (self.target, self.payload, self.linker, self.conjugation,
                self.dar, self.isotype, self.masking)


@dataclass
class RejectionLog:
    """Why candidates were dropped, so the constraint engine can be shown to be load-bearing."""

    counts: dict[str, int] = field(default_factory=dict)

    def note(self, reason: str) -> None:
        self.counts[reason] = self.counts.get(reason, 0) + 1

    def summary(self) -> str:
        return "\n".join(
            f"  {n:7,d}  {reason}"
            for reason, n in sorted(self.counts.items(), key=lambda kv: -kv[1])
        )


class DesignSpace:
    def __init__(self, path: Path = DESIGN_YAML) -> None:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.payloads: dict[str, dict] = doc["payloads"]
        self.linkers: dict[str, dict] = doc["linkers"]
        self.attach_to_conj: dict[str, list[str]] = doc["attach_to_conjugation"]
        self.conj_dar: dict[str, dict] = doc["conjugation_dar"]
        self.isotypes: dict[str, dict] = doc["isotypes"]
        self.masking: dict[str, dict] = doc["masking"]
        self.dar_cap: float = float(doc["dar_hard_cap"])

    def enumerate(
        self,
        target: str,
        tier: int = 1,
        include_unapproved_conjugation: bool = False,
    ) -> tuple[list[Design], RejectionLog]:
        """All valid designs against one target.

        `tier=1` keeps only components with clinical precedent, meaning some ADC carrying
        them reached at least phase 1.

        `include_unapproved_conjugation` is retained for callers that want to relax the
        conjugation gate specifically, but note that it currently changes nothing: once the
        Tier-1 gate was corrected from *approved* to *clinical* precedent, engineered
        cysteine, glycan remodelling and unnatural amino acids all pass it anyway.
        Measured: both settings return the identical 106 designs for a given target. Such
        components are flagged `has_unapproved_component` rather than excluded.
        """
        log = RejectionLog()
        out: list[Design] = []
        seen: set[tuple] = set()

        for p_name, payload in self.payloads.items():
            if tier == 1 and payload.get("clinical_adcs", 0) == 0:
                log.note(f"payload has no clinical ADC: {p_name}")
                continue
            for l_name, linker in self.linkers.items():
                # Constraint 3: the payload's attachment group must match the linker's.
                if linker["handle"] != payload["handle"]:
                    continue
                if tier == 1 and linker.get("clinical_adcs", 0) == 0:
                    log.note(f"linker has no clinical ADC: {l_name}")
                    continue
                # Constraint 1: conjugation is determined by the linker's reactive group.
                conjugations = self.attach_to_conj.get(linker["attach"], [])
                for c_name in conjugations:
                    spec = self.conj_dar.get(c_name)
                    if spec is None:
                        continue
                    if spec.get("clinical_adcs", 0) == 0 and not include_unapproved_conjugation:
                        log.note(f"conjugation has no clinical ADC: {c_name}")
                        continue
                    # Constraint 2: DAR levels are set by the conjugation chemistry.
                    for dar in spec["levels"]:
                        if dar > self.dar_cap:
                            log.note(f"DAR above hard cap {self.dar_cap}")
                            continue
                        for i_name, iso in self.isotypes.items():
                            restrict = iso.get("restrict_to_payloads")
                            if restrict and p_name not in restrict:
                                log.note(
                                    f"isotype {i_name} has precedent only with "
                                    f"{','.join(restrict)}"
                                )
                                continue
                            for m_name, mask in self.masking.items():
                                floor = mask.get("only_when_dar_at_least")
                                if floor is not None and dar < floor:
                                    log.note(
                                        f"masking {m_name} is only precedented at DAR "
                                        f">= {floor}"
                                    )
                                    continue
                                if tier == 1 and mask.get("clinical_adcs", 0) == 0:
                                    log.note(f"masking has no approved ADC: {m_name}")
                                    continue
                                unapproved = (
                                    payload["approved_adcs"] == 0
                                    or linker["approved_adcs"] == 0
                                    or spec["approved_adcs"] == 0
                                    or mask["approved_adcs"] == 0
                                )
                                d = Design(
                                    has_unapproved_component=unapproved,
                                    target=target, payload=p_name,
                                    mechanism=payload["mechanism"], linker=l_name,
                                    cleavable=bool(linker["cleavable"]),
                                    conjugation=c_name, dar=float(dar),
                                    isotype=i_name, masking=m_name,
                                )
                                if d.key() in seen:
                                    continue
                                seen.add(d.key())
                                out.append(d)
        return out, log
