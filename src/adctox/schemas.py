"""Request and response schemas. One definition, shared by the API, the dataset and the model.

The scope constraint is enforced **here**, structurally, rather than by copy elsewhere:
there is no free-text field anywhere in a request except the payload SMILES, which is
chemistry, not a person. Every patient-side field is an enum or a bounded number, so a
patient identifier is not representable. `tests/test_schemas.py` asserts that property,
which makes it something a reader can verify by running one test rather than something
they have to take on trust.

Two further structural choices:

* Comorbidities come from a closed registry; an unknown id is a 422, not a shrug.
* Nothing is persisted. `assessment_id` is a correlation handle, not a record locator.
"""

from __future__ import annotations

import csv
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONF = Path(__file__).resolve().parents[2] / "conf"


@lru_cache(maxsize=1)
def comorbidity_registry() -> dict[str, dict]:
    """The closed comorbidity list, validated at load.

    The axis names are checked against the ontology here, loudly, because getting one
    wrong is silent in two contradictory directions and announces neither. Measured on a
    deliberate typo: `comorbidity_weights` iterates the fourteen real axes and never looks
    up the misspelled one, so the patient's declared vulnerability becomes completely
    inert with every weight at 1.0 -- while constraint C6 iterates the at-risk set and
    rejects every candidate design for having no evidence on an organ that does not exist.
    One typo, and the system either ignores the comorbidity or refuses to answer, with no
    indication which. This is the same failure shape as the axis ontology's own
    comma-splitting bug, which silently emptied the pulmonary axis.
    """
    from .taxonomy import default_taxonomy

    known = set(default_taxonomy().axis_order)
    rows: dict[str, dict] = {}
    with (CONF / "comorbidity_registry.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            axes = [a.strip() for a in row["organ_axes"].split(";") if a.strip()]
            if not axes:
                raise ValueError(
                    f"comorbidity {row['id']!r} declares no organ axis, so it can never "
                    "weight anything. Give it an axis or remove it."
                )
            unknown = sorted(set(axes) - known)
            if unknown:
                raise ValueError(
                    f"comorbidity {row['id']!r} references organ axes {unknown} that are "
                    f"not in the ontology. Known axes: {sorted(known)}. Left unchecked "
                    "this is silent: the condition stops weighting anything and C6 "
                    "simultaneously rejects every design for lack of evidence on it."
                )
            if not (row.get("severity_basis") or "").strip():
                raise ValueError(
                    f"comorbidity {row['id']!r} has no severity_basis. The severity is an "
                    "elicited prior with no training rows, so an unsourced number is not "
                    "defensible."
                )
            severity = float(row["severity"])
            if not 0.0 < severity <= 1.0:
                raise ValueError(
                    f"comorbidity {row['id']!r} has severity {severity}, outside (0, 1]. "
                    "It scales the objective weight as 1 + lambda*severity."
                )
            row["organ_axes"] = axes
            row["severity"] = severity
            rows[row["id"]] = row
    return rows


# The accepted comorbidity list is closed at the *type* level, not merely checked at
# runtime. Building the enum from the registry means the closed-list property is
# structural -- it appears in the OpenAPI schema and in the generated TypeScript client,
# so a caller cannot construct an out-of-list value in the first place. An earlier version
# used `list[str]` with a validator; a schema test flagged that as a free string field,
# which it was.
ComorbidityId = Enum(  # type: ignore[misc]
    "ComorbidityId",
    {cid: cid for cid in comorbidity_registry()},
    type=str,
)
ComorbidityId.__doc__ = (
    "Closed list of accepted comorbidities, generated from conf/comorbidity_registry.csv."
)


class AgeBand(str, Enum):
    """Coarse bands only. A date of birth or an exact age would be identifying, and the
    model has no use for the resolution anyway."""

    under_40 = "under_40"
    b40_54 = "40_54"
    b55_64 = "55_64"
    b65_74 = "65_74"
    b75_plus = "75_plus"


class Sex(str, Enum):
    female = "female"
    male = "male"
    unspecified = "unspecified"


class Mechanism(str, Enum):
    tubulin = "tubulin"
    topo1 = "topo1"
    dna_cleave = "dna_cleave"
    dna_crosslink = "dna_crosslink"
    dna_alkyl = "dna_alkyl"
    protein_synth = "protein_synth"
    photo = "photo"


class Conjugation(str, Enum):
    lysine = "lysine"
    interchain_cysteine = "interchain_cysteine"
    engineered_cysteine = "engineered_cysteine"
    glycan = "glycan"
    unnatural_aa = "unnatural_aa"


class Isotype(str, Enum):
    IgG1 = "IgG1"
    IgG4 = "IgG4"


class Masking(str, Enum):
    none = "none"
    PEG = "PEG"


class Cohort(BaseModel):
    """Coarse demographics, labelled for what they are: cohort matching, not a patient."""

    model_config = ConfigDict(extra="forbid")
    age_band: AgeBand | None = None
    sex: Sex | None = None


class ComorbidityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conditions: list[ComorbidityId] = Field(default_factory=list, max_length=20)
    cohort: Cohort | None = None

    @field_validator("conditions")
    @classmethod
    def _dedupe(cls, v: list[ComorbidityId]) -> list[ComorbidityId]:
        return list(dict.fromkeys(v))

    @property
    def condition_ids(self) -> list[str]:
        return [c.value for c in self.conditions]


class ADCDesign(BaseModel):
    """A fully specified design, for the expert mode. Every slot is an enum or bounded."""

    model_config = ConfigDict(extra="forbid")
    target_antigen: str = Field(max_length=24, pattern=r"^[A-Za-z0-9\-]+$")
    payload: str = Field(max_length=32, pattern=r"^[A-Za-z0-9\-]+$")
    linker: str = Field(max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    conjugation: Conjugation
    dar: float = Field(ge=0.5, le=8.0)
    isotype: Isotype = Isotype.IgG1
    masking: Masking = Masking.none


class ProposeRequest(BaseModel):
    """The primary path: comorbidity profile plus a target, nothing else."""

    model_config = ConfigDict(extra="forbid")
    comorbidity_profile: ComorbidityProfile
    target_antigen: str = Field(max_length=24, pattern=r"^[A-Za-z0-9\-]+$")
    top_k: int = Field(default=6, ge=1, le=20)


class AssessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design: ADCDesign
    comorbidity_profile: ComorbidityProfile


class Interval(BaseModel):
    lo: float
    hi: float
    kind: Literal["credible_90"] = "credible_90"


class Driver(BaseModel):
    """One contribution to an organ risk, carrying where it came from.

    `source` is not decoration. The comorbidity layer has no training data -- zero trials
    report comorbidity-stratified organ rates -- so it is an elicited prior and must never
    be shown as though it were fitted. Keeping the provenance machine-readable is what
    lets the UI colour them apart.
    """

    factor: str
    source: Literal[
        "model", "exclusion_head", "elicited_prior", "rule", "target_expression"
    ]
    # None where the driver is not a term in the linear predictor -- a label rule and an
    # exclusion-criteria prior both change what is shown without adding a logit. 0.0 would
    # read as a measured contribution of nothing, which is a different and false claim.
    contribution: float | None
    detail: str | None = None
    odds_ratio: float | None = None
    # Carried for the exclusion prior, whose ratios are selected on magnitude AND on
    # surviving Benjamini-Hochberg correction across all 66 (mechanism, organ) cells.
    # Shown because a 13x ratio on a single-drug mechanism is cheap, and three such cells
    # were being served before the correction was applied.
    p_value: float | None = None
    # Target-expression percentile, for the on-target off-tumour flag.
    percentile: float | None = None
    quote: str | None = None
    flag_id: str | None = None
    tier: str | None = None

    # Closed so that a field added to a response without being declared here fails the
    # contract test, rather than passing silently as it did while nothing validated these
    # models at all.
    model_config = ConfigDict(extra="forbid")


class OrganRisk(BaseModel):
    organ_axis: str
    label: str
    # Any-grade rate from the otherEvents table. None at novelty tier 3, and None where
    # the corpus has too few arms to support a number.
    point_estimate: float | None
    # Serious-event rate for the same axis, from the seriousEvents table. Reported
    # alongside rather than instead, because the two answer different questions and,
    # measured on this corpus, rank organs differently: topo-I payloads sit 10th of 14 on
    # pulmonary in the common table and 2nd in the serious one. None when the serious fit
    # is absent or too thin on this axis.
    serious_estimate: float | None = None
    # The serious rate's own credible interval. Required by the same rule as the
    # any-grade one: a point estimate without an interval overstates what is known, and
    # the serious row is the one a vulnerable patient reads first.
    serious_interval: Interval | None = None
    interval: Interval
    risk_band: Literal["low", "moderate", "high", "no_evidence"]
    # Which table the band was computed on. An axis the patient is vulnerable on is a
    # serious-harm question and is banded on the serious table; the rest are tolerability.
    # Bands are not comparable across bases -- each table has its own measured edges.
    band_basis: Literal["common", "serious"] = "common"
    # Whether the band came from the fit or was raised by a label rule. The first thing a
    # reviewer asks about a red axis.
    band_source: Literal["model", "rule"] = "model"
    weight_applied: float
    n_supporting_agents: int
    n_supporting_arms: int
    at_risk_for_patient: bool = False
    drivers: list[Driver] = Field(default_factory=list)
    # The exact additive waterfall check: the drivers' sum against the reported rate, and
    # the Jensen gap between them. Stated rather than hidden, because the mean of a
    # transformed draw is not the transform of the mean.
    driver_sum: dict | None = None

    model_config = ConfigDict(extra="forbid")


class Coverage(BaseModel):
    """Novelty tiering and the out-of-distribution refusal.

    Tier 1 is a new combination of precedented parts and is the only tier the product
    claims. Tier 2 (a new molecule in a known family) is not supported: the chemistry
    corpus has no relatives for 9 of 11 payload classes. Tier 3 gets no point estimate.
    """

    novelty_tier: Literal[1, 2, 3]
    in_distribution: bool
    # Whether any corpus agent targets this antigen. Reported for context only: the
    # target does not enter the organ estimate, since target x axis interactions were
    # dropped as near-collinear with payload family.
    target_in_corpus: bool | None = None
    nearest_reference_adcs: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ComorbidityOverlap(BaseModel):
    condition: str
    organ_axis: str
    concern_level: Literal["low", "moderate", "high"]
    rationale: str
    source: Literal["elicited_prior"] = "elicited_prior"
    caveat: str = (
        "Organ-system intersection only. There is no interaction model and no "
        "patient-level data; the weighting is a declared preference, not a fitted effect."
    )


class Disclaimer(BaseModel):
    id: str = "scope_v1"
    severity: Literal["blocking"] = "blocking"
    text: str = (
        "Research prototype. Not a clinical decision tool and not for use in patient "
        "care. Outputs are relative rankings over published trial data, not probabilities "
        "of harm for an individual."
    )


class AssessResponse(BaseModel):
    assessment_id: str
    model_version: str
    corpus_version: str
    disclaimer: Disclaimer = Field(default_factory=Disclaimer)
    limitations: list[str] = Field(default_factory=list)
    organ_risks: list[OrganRisk]
    comorbidity_overlaps: list[ComorbidityOverlap] = Field(default_factory=list)
    coverage: Coverage
    interpretation: Literal["relative_ranking_only"] = "relative_ranking_only"


class Candidate(BaseModel):
    rank: int
    tie_group: int
    # Pairwise: this candidate's tie group holds only itself.
    distinguishable: bool
    # The head of the list only, null for every other candidate: whether the leader beats
    # the runner-up on enough paired draws to be printed as a winner, and on what fraction.
    # Separate from `distinguishable` because a leader alone in its tie group can still
    # fail this, and one flag covering both said "not distinguishable from its group" about
    # a group of one.
    lead_is_decisive: bool | None = None
    lead_p: float | None = None
    # How many candidates share this rank.
    group_size: int | None = None
    # Non-null only inside a group of more than one: what orders the group, given that the
    # patient-weighted risk could not. A stated preference, never a confidence ordering.
    secondary_order_basis: str | None = None
    design: dict
    organ_risks: list[OrganRisk]
    weighted_risk: float
    worst_axis: str
    worst_axis_risk: float
    precedent_score: float
    binding_constraint: str | None
    nearest_real_adc: str | None
    nearest_real_diff: str | None
    novelty_tier: Literal[1, 2, 3]
    has_unapproved_component: bool


class ProposeResponse(BaseModel):
    proposal_id: str
    model_version: str
    corpus_version: str
    disclaimer: Disclaimer = Field(default_factory=Disclaimer)
    limitations: list[str] = Field(default_factory=list)
    n_enumerated: int
    n_passed_constraints: int
    candidates: list[Candidate]
    # Positions within `candidates`, not indices into the full enumeration.
    pareto_front: list[int]
    # How many non-dominated candidates exist in total, which is usually larger
    # than what fits in `candidates` and says how much choice was left unshown.
    n_pareto_front: int = 0
    tie_groups: list[list[int]]
    weights_applied: dict[str, float]
    why_not_the_obvious_one: dict | None = None
    ranking_caveat: str = (
        "Ranks are ordinal and comparable only within this proposal. Candidates sharing a "
        "rank have overlapping posteriors and are not distinguishable."
    )
    claimed: str = (
        "Among chemically valid, individually precedented configurations for this target, "
        "these are the ones whose predicted organ-toxicity profile is least likely to "
        "worsen the stated organ impairments, conditional on the forward model."
    )
    not_claimed: list[str] = Field(
        default_factory=lambda: [
            "That any proposal is efficacious. No efficacy model is used.",
            "That the ordering within a tie group is meaningful.",
            "That the comorbidity weighting is learned. It is an elicited prior.",
            "Any extrapolation to payload mechanisms absent from the training corpus.",
            "Anything about Fc engineering, which is not offered as a design slot.",
        ]
    )
