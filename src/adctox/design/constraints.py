"""Hard pass/fail constraints on a candidate ADC design.

These are constraints, not penalties, and that distinction is load-bearing. Ranking
purely on "lowest predicted toxicity" degenerates immediately to the least potent
payload at the lowest DAR with a non-cleavable linker -- a safe drug that does nothing.
Efficacy cannot be used to stop that, because it is not predictable from public data:
on the one public ADC activity dataset (435 rows), a decision tree on SMILES string
length and DAR beats an ESM-2 plus chemical-BERT model under a leakage-free grouped
split (0.811 vs 0.758 AUC, winning 4 of 5 folds). An objective you cannot predict better
than string length is not an objective.

So potency enters as a floor instead: a candidate must clear a delivered-cytotoxic-dose
threshold set at the 10th percentile of *approved* ADCs. That threshold is computed from
the registry rather than asserted, so there is no arbitrary constant to argue about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from .enumerate import Design

REGISTRY_YAML = Path(__file__).resolve().parents[3] / "conf" / "adc_registry.yaml"
DESIGN_YAML = Path(__file__).resolve().parents[3] / "conf" / "design_space.yaml"


@dataclass
class ConstraintResult:
    passed: bool
    failures: list[str]
    margins: dict[str, float]

    @property
    def binding(self) -> str | None:
        """The constraint that came closest to failing, for display.

        Showing this is what demonstrates the constraints are load-bearing rather than
        decorative -- a reader can see which one actually bit.
        """
        if not self.margins:
            return None
        return min(self.margins, key=self.margins.get)


class ConstraintEngine:
    def __init__(
        self,
        design_yaml: Path = DESIGN_YAML,
        registry_yaml: Path = REGISTRY_YAML,
    ) -> None:
        doc = yaml.safe_load(design_yaml.read_text(encoding="utf-8"))
        self.payloads = doc["payloads"]
        self.linkers = doc["linkers"]
        self.dar_cap = float(doc["dar_hard_cap"])
        reg = yaml.safe_load(registry_yaml.read_text(encoding="utf-8"))["agents"]

        # C2 threshold, computed not asserted: delivered dose is DAR / IC50, and the floor
        # is the 10th percentile over approved ADCs whose payload appears in the design
        # space. Using approved ADCs as the reference means the floor means something
        # clinically rather than being a round number someone picked.
        delivered = []
        for spec in reg.values():
            if not spec.get("first_us_approval") or not spec.get("conventional_adc"):
                continue
            p = self.payloads.get(spec["payload"])
            if p is None:
                continue
            delivered.append(spec["dar"] / p["ic50_nm"])
        self.delivered_dose_floor = float(np.percentile(delivered, 10)) if delivered else 0.0
        self.n_reference_adcs = len(delivered)

    def delivered_dose(self, design: Design) -> float:
        return design.dar / self.payloads[design.payload]["ic50_nm"]

    def check(
        self,
        design: Design,
        at_risk_axes: set[str] | None = None,
        selectivity: dict[str, float] | None = None,
        max_ic50_nm: float = 1000.0,
        evidence_arms: dict[str, int] | None = None,
        min_arms: int = 3,
    ) -> ConstraintResult:
        """Evaluate every constraint. `margins` are normalized slack, higher is safer."""
        failures: list[str] = []
        margins: dict[str, float] = {}
        payload = self.payloads[design.payload]

        # C1: free-payload potency. A generous absolute ceiling; C2 does the real work.
        ic50 = payload["ic50_nm"]
        margins["C1_payload_potency"] = float(np.log10(max_ic50_nm / max(ic50, 1e-6)))
        if ic50 > max_ic50_nm:
            failures.append(f"C1 payload IC50 {ic50} nM exceeds {max_ic50_nm} nM")

        # C2: delivered cytotoxic dose relative to approved ADCs. Blocks the "lowest DAR,
        # weakest payload" degenerate solution.
        dd = self.delivered_dose(design)
        margins["C2_delivered_dose"] = float(
            np.log10(max(dd, 1e-9) / max(self.delivered_dose_floor, 1e-9))
        )
        if dd < self.delivered_dose_floor:
            failures.append(
                f"C2 delivered dose {dd:.3g} below the approved-ADC 10th percentile "
                f"{self.delivered_dose_floor:.3g}"
            )

        # C3: target selectivity against the organs this patient cannot afford. Only
        # bites for a bystander-permeable payload, since a non-permeable one cannot
        # reach neighbouring tissue. Selectivity is a flag, never a ranking key: GTEx
        # reports ERBB2 at a median 86.7 TPM in aorta, which would call HER2 "an artery
        # gene" -- real HER2 cardiotoxicity is cardiomyocyte, not aortic smooth muscle.
        if at_risk_axes and selectivity and payload.get("membrane_permeable"):
            worst = min(
                (selectivity[a] for a in at_risk_axes if a in selectivity), default=None
            )
            if worst is not None:
                margins["C3_selectivity"] = float(worst - 1.0)
                if worst < 1.0:
                    failures.append(
                        f"C3 selectivity index {worst:.2f} below 1.0 on an at-risk organ "
                        "with a bystander-permeable payload"
                    )

        # C5: chemistry validity. The enumerator already enforces this, so a failure here
        # means a design was constructed by hand or by a caller that bypassed it.
        linker = self.linkers[design.linker]
        if linker["handle"] != payload["handle"]:
            failures.append(
                f"C5 linker {design.linker} expects a {linker['handle']} handle, "
                f"{design.payload} presents {payload['handle']}"
            )
        if design.dar > self.dar_cap:
            failures.append(f"C5 DAR {design.dar} above hard cap {self.dar_cap}")
        margins["C5_dar_headroom"] = float(self.dar_cap - design.dar)

        # C6: the system must be able to speak to the question it was asked. If an organ
        # the patient cannot afford has no evidence for this chemistry, the candidate is
        # not safer than its rivals -- it is unstudied, and ranking it as though the two
        # were the same rewards ignorance.
        if at_risk_axes and evidence_arms is not None:
            thin = sorted(
                a for a in at_risk_axes if evidence_arms.get(a, 0) < min_arms
            )
            worst = min((evidence_arms.get(a, 0) for a in at_risk_axes), default=min_arms)
            margins["C6_evidence_on_at_risk_axes"] = float(worst - min_arms)
            if thin:
                failures.append(
                    f"C6 no usable evidence for this chemistry on "
                    f"{', '.join(thin)}, which this profile flags as at risk "
                    f"(fewer than {min_arms} supporting arms)"
                )

        return ConstraintResult(not failures, failures, margins)
