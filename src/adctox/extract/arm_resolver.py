"""Attribute ClinicalTrials.gov event groups to a single ADC agent.

The problem this solves, measured on 605 ADC studies: ``adverseEventsModule.eventGroups``
carries **no foreign key** to ``armsInterventionsModule.armGroups``. Its fields are only
id / title / description / the three at-risk denominators. Matching the event-group title
to an arm-group label exactly succeeds for just 22.4% of groups; the rest are free text
like "Arm I", "5 mcg/kg", "Cohort 3".

Every design feature the forward model uses (payload, mechanism, linker, DAR, isotype)
lives at agent level, so attribution is the gate on the entire design matrix. A naive
regex over drug names is not enough and is actively dangerous: a loose code-name match
reported 52 of 54 agents as having extractable data where strict attribution found 13,
i.e. a 75% false-positive rate driven by review articles and by substring collisions
(``irinotecan`` matching a ``tecan`` pattern).

Resolution runs in precedence order, most trustworthy first, and every row records which
layer fired so the result can be audited:

1. ``title_named``   -- the event-group title or description names an agent outright.
                        Measured as the single most productive layer.
2. ``join_exact``    -- title equals an arm-group label verbatim.
3. ``join_ci``       -- equal after casefold + punctuation normalization.
4. ``join_fuzzy``    -- token-set overlap above a threshold.
5. ``trial_single``  -- the trial involves exactly one ADC, so any ADC-bearing arm is it.

Groups that resolve to no agent are mostly legitimate non-ADC comparator arms (ABVD,
docetaxel, "Treatment of Physician's Choice") and are reported separately from genuinely
unattributable ones, because conflating them makes the join look far worse than it is.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REGISTRY_YAML = Path(__file__).resolve().parents[3] / "conf" / "adc_registry.yaml"

# Non-ADC agents whose names appear in arm titles. Used only to tell a legitimate
# comparator arm apart from an unattributable one -- never for attribution itself.
_COMPARATOR_HINTS = (
    "physician", "chemotherapy", "standard of care", "standard arm", "investigator",
    "placebo", "best supportive", "observation", "docetaxel", "paclitaxel", "carboplatin",
    "cisplatin", "doxorubicin", "cyclophosphamide", "vincristine", "rituximab",
    "bendamustine", "dacarbazine", "cytarabine", "daunorubicin", "abvd", "chop", "ice",
    "capecitabine", "eribulin", "gemcitabine", "vinorelbine", "lapatinib", "trastuzumab",
    "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "osimertinib",
)

_PUNCT = re.compile(r"[^\w\s]+")
_WS = re.compile(r"\s+")


def _norm(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip().casefold()


def _tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _norm(text).split() if len(t) > 2)


@dataclass
class Registry:
    """Agent aliases compiled into matchers, longest alias first."""

    agents: dict[str, dict]
    _patterns: list[tuple[re.Pattern[str], str]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path = REGISTRY_YAML) -> "Registry":
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        reg = cls(agents=doc["agents"])
        pairs: list[tuple[str, str]] = []
        for key, spec in doc["agents"].items():
            for alias in spec["aliases"]:
                pairs.append((_norm(alias), key))
        # Longest alias first so "trastuzumab deruxtecan" wins over "trastuzumab".
        pairs.sort(key=lambda p: -len(p[0]))
        for alias, key in pairs:
            # \b on both sides blocks the substring collisions that produced the 75%
            # false-positive rate (e.g. `tecan` inside `irinotecan`).
            reg._patterns.append((re.compile(rf"\b{re.escape(alias)}\b"), key))
        return reg

    def find_agents(self, *texts: str | None) -> list[str]:
        """Agent keys named anywhere in the given texts, in first-match order."""
        blob = " ".join(_norm(t) for t in texts if t)
        found: list[str] = []
        for pattern, key in self._patterns:
            if key in found:
                continue
            if pattern.search(blob):
                found.append(key)
        return found

    def mechanism(self, agent: str) -> str:
        return self.agents[agent]["mechanism"]


@dataclass
class ResolvedArm:
    nct_id: str
    group_id: str
    title: str
    description: str
    n_at_risk_other: int | None
    n_at_risk_serious: int | None
    agent: str | None
    layer: str
    combo_agents: tuple[str, ...]
    is_monotherapy: bool | None
    is_comparator: bool
    matched_arm_label: str | None


def _arm_labels(study: dict) -> list[tuple[str, str]]:
    """(label, description) for every armGroup in a study."""
    arms = (
        (study.get("protocolSection") or {}).get("armsInterventionsModule") or {}
    ).get("armGroups") or []
    out = []
    for arm in arms:
        out.append((arm.get("label") or "", arm.get("description") or ""))
    return out


def _intervention_names(study: dict) -> list[str]:
    ivs = (
        (study.get("protocolSection") or {}).get("armsInterventionsModule") or {}
    ).get("interventions") or []
    names: list[str] = []
    for iv in ivs:
        if iv.get("name"):
            names.append(iv["name"])
        names.extend(iv.get("otherNames") or [])
    return names


def resolve_study(study: dict, registry: Registry, fuzzy_threshold: float = 0.6) -> list[ResolvedArm]:
    """Resolve every event group in one study to an agent, or to None with a reason."""
    proto = study.get("protocolSection") or {}
    nct = (proto.get("identificationModule") or {}).get("nctId", "")
    ae = (study.get("resultsSection") or {}).get("adverseEventsModule") or {}
    groups = ae.get("eventGroups") or []
    if not groups:
        return []

    arms = _arm_labels(study)
    arm_by_norm = {_norm(label): (label, desc) for label, desc in arms}
    # Agents named anywhere in the trial, used by the trial_single fallback.
    trial_agents = registry.find_agents(
        *_intervention_names(study),
        *(label for label, _ in arms),
        *(desc for _, desc in arms),
    )

    resolved: list[ResolvedArm] = []
    for group in groups:
        title = group.get("title") or ""
        desc = group.get("description") or ""

        agent: str | None = None
        layer = "unresolved"
        matched_label: str | None = None
        # Agents visible from this group's own text plus whichever arm it joins to.
        scope_texts: list[str] = [title, desc]

        # Layer 1: the group text names an agent.
        named = registry.find_agents(title, desc)
        if named:
            agent, layer = named[0], "title_named"

        # Layers 2-4: join to an arm group, then read agents off the arm.
        key = _norm(title)
        join_label = None
        if key and key in arm_by_norm:
            join_label, join_desc = arm_by_norm[key]
            join_layer = "join_exact" if title == join_label else "join_ci"
        else:
            join_desc = ""
            join_layer = None
            best, best_score = None, 0.0
            group_tokens = _tokens(title)
            if group_tokens:
                for norm_label, (label, adesc) in arm_by_norm.items():
                    arm_tokens = _tokens(label)
                    if not arm_tokens:
                        continue
                    score = len(group_tokens & arm_tokens) / len(group_tokens | arm_tokens)
                    if score > best_score:
                        best, best_score = (label, adesc), score
            if best and best_score >= fuzzy_threshold:
                join_label, join_desc = best
                join_layer = "join_fuzzy"

        if join_label is not None:
            scope_texts.extend([join_label, join_desc])
            matched_label = join_label
            if agent is None:
                via_arm = registry.find_agents(join_label, join_desc)
                if via_arm:
                    agent, layer = via_arm[0], join_layer or "join_exact"

        # Layer 5: exactly one ADC in the whole trial.
        if agent is None and len(trial_agents) == 1:
            blob = _norm(" ".join(t for t in scope_texts if t))
            if blob and not any(h in blob for h in _COMPARATOR_HINTS):
                agent, layer = trial_agents[0], "trial_single"

        # Combination detection: other ADCs named in scope, plus comparator-drug hints.
        scope_agents = registry.find_agents(*scope_texts)
        combo = tuple(a for a in scope_agents if a != agent)
        blob = _norm(" ".join(t for t in scope_texts if t))
        has_other_drug = any(h in blob for h in _COMPARATOR_HINTS)
        is_mono = None if agent is None else not (combo or has_other_drug)
        is_comparator = agent is None and has_other_drug

        if agent is None:
            layer = "comparator" if is_comparator else "unattributable"

        resolved.append(
            ResolvedArm(
                nct_id=nct,
                group_id=group.get("id") or "",
                title=title,
                description=desc,
                n_at_risk_other=group.get("otherNumAtRisk"),
                n_at_risk_serious=group.get("seriousNumAtRisk"),
                agent=agent,
                layer=layer,
                combo_agents=combo,
                is_monotherapy=is_mono,
                is_comparator=is_comparator,
                matched_arm_label=matched_label,
            )
        )
    return resolved
