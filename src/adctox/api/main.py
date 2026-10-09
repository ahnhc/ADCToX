"""FastAPI app. The scope constraint is carried in the payload, not only in the UI.

Every response embeds the disclaimer and the limitations list, so bypassing the frontend
does not bypass the framing. Nothing is persisted: the ids in responses are correlation
handles, not record locators.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from ..design.enumerate import DesignSpace
from ..model.predict import Posterior
from ..pipeline import propose, resolve_comorbidities
from ..schemas import AssessRequest, Disclaimer, ProposeRequest, comorbidity_registry
from ..taxonomy import default_taxonomy

ROOT = Path(__file__).resolve().parents[3]
CONF = ROOT / "conf"
ARTIFACTS = ROOT / "artifacts"

def _registry_targets() -> set[str]:
    """Targets some ADC has been built against, from the registry.

    Named for what it reads. It was `_targets_in_corpus`, which claimed more: the registry
    holds 35 agents and the fit sees 16 of them, so a target can be in here and carry no
    fitted arm at all. Nothing downstream wanted the stronger claim -- the comparison set it
    guards is also registry-based -- but a name that overstates its own scope is how a later
    reader comes to rely on the stronger one.
    """
    return {
        str(spec.get("target")).upper()
        for spec in _registry().values()
        if spec.get("target")
    }


def _coverage(design, family: str, post) -> dict:
    """Novelty tier plus what the estimate actually rests on.

    Two distinctions the earlier version collapsed. A payload family absent from the
    corpus is a real limitation; a known family whose particular molecule has no arm is
    a different and milder one, and both were previously reported as nothing at all or as
    an unsupported tier.
    """
    refs = _reference_adcs(design.payload, family, design.mechanism)
    in_corpus = family in post.families
    same_payload = [r for r in refs if r["relation"] == "same payload"]
    warnings = []
    # The target does not enter the organ estimate at all. Target x axis interactions were
    # removed as near-collinear with payload family -- eight of the corpus's families map
    # almost one-to-one onto a target -- so the figures below describe the chemistry and
    # are identical for every target. Said out loud because the endpoint accepts any
    # well-formed antigen name and returns fourteen confident numbers, and a caller who
    # named their target would otherwise reasonably assume it was used.
    known_target = str(design.target).upper() in _registry_targets()
    warnings.append(
        "the target antigen does not enter these estimates: target x axis interactions "
        "were dropped as near-collinear with payload family, so the same chemistry "
        "returns the same organ profile for every target"
        + ("" if known_target else
           f". {design.target!r} is also absent from the corpus, so no agent "
           "against it informs the comparison set below")
    )
    if not in_corpus:
        warnings.append(
            f"payload family {family or '(unmapped)'!r} is absent from the training "
            "corpus; the estimate falls back to its mechanism"
        )
    elif not same_payload:
        warnings.append(
            f"no agent in the corpus carries {design.payload}; the estimate is the "
            f"{family} / {design.mechanism} effect, shared with "
            + ", ".join(r["agent"] for r in refs[:3])
            + ". The payload level is not identified in this corpus, so two payloads in "
            "one family receive the same organ profile by construction."
        )
    return {
        "novelty_tier": 1 if in_corpus else 2,
        "in_distribution": in_corpus,
        "target_in_corpus": known_target,
        "nearest_reference_adcs": refs,
        "warnings": warnings,
    }


def _verdict(delta: float | None, ci: list | None) -> str:
    """Read the verdict off the interval, so prose cannot drift from the number."""
    if delta is None or not ci or len(ci) != 2 or ci[0] is None:
        return "not computed"
    lo, hi = ci
    if lo > 0:
        return "model beats the baseline"
    if hi < 0:
        return "model loses to the baseline"
    return "indistinguishable from the baseline; the interval includes zero"


@lru_cache(maxsize=1)
def _ranking_evidence() -> dict:
    """What the ordering is actually worth, measured, served with every ranking.

    Every evaluation travels with the output, including the ones that disagree, because a
    caller who sees only a ranking would read far more into it than the evidence carries.

    Verdicts are derived from each interval rather than written as prose. They had drifted:
    this function told callers the model "beats the baseline" on dose-modification
    ordering while the model card said that comparison stopped being favourable after the
    centering-bug fix. The model card was right -- the paired delta is
    +0.0348 [-0.0007, +0.0693], which includes zero -- and a hand-written verdict is how
    the two came to disagree. So the wording now follows the numbers.
    """
    out: dict = {"evaluations": []}
    fw = ARTIFACTS / "forward_other_metrics.json"
    if fw.exists():
        doc = json.loads(fw.read_text(encoding="utf-8"))
        for split, res in (doc.get("cv") or {}).items():
            out["evaluations"].append(
                {
                    "name": f"within-arm axis ranking, {split}",
                    "metric": "AUROC for axis in the arm's observed top 3",
                    "direction": "higher_is_better",
                    "model": res.get("macro_auc"),
                    "best_baseline": max(
                        res.get("macro_auc_mech_baseline") or 0,
                        res.get("macro_auc_global_baseline") or 0,
                    ),
                    "delta": res.get("delta_auc_mean"),
                    "delta_ci": res.get("delta_auc_ci"),
                    "verdict": _verdict(
                        res.get("delta_auc_mean"), res.get("delta_auc_ci")
                    ),
                }
            )
            aas = res.get("across_agent_spearman") or {}
            if aas.get("applicable") is False:
                # Reported rather than dropped: a caller must be able to tell a split the
                # metric does not apply to from one where it was never computed.
                out["evaluations"].append(
                    {
                        "name": f"across-agent per-axis discrimination, {split}",
                        "metric": "mean Spearman across agents within an axis",
                        "direction": "higher_is_better",
                        "model": None,
                        "verdict": f"not applicable -- {aas.get('reason', '')}",
                    }
                )
            elif aas.get("model_mean") is not None:
                out["evaluations"].append(
                    {
                        "name": f"across-agent per-axis discrimination, {split}",
                        "metric": "mean Spearman across agents within an axis",
                        "direction": "higher_is_better",
                        "model": aas["model_mean"],
                        "verdict": "at chance; the pre-declared threshold was +0.3",
                    }
                )
    dm = ARTIFACTS / "dose_mod_eval.json"
    if dm.exists():
        doc = json.loads(dm.read_text(encoding="utf-8"))
        out["evaluations"].append(
            {
                "name": "agreement with approved dose-modification orderings",
                "metric": "mean Spearman against label organ-severity ordering",
                "direction": "higher_is_better",
                "model": doc.get("mean_rho_model"),
                "best_baseline": max(
                    doc.get("mean_rho_mech_baseline") or 0,
                    doc.get("mean_rho_global_baseline") or 0,
                ),
                "delta": doc.get("paired_delta_vs_best_baseline"),
                "delta_ci": doc.get("paired_delta_ci"),
                "top_organ_agreement": doc.get("top_organ_agreement"),
                "verdict": (
                    _verdict(
                        doc.get("paired_delta_vs_best_baseline"),
                        doc.get("paired_delta_ci"),
                    )
                    + "; and at chance on naming the organ the label fears most "
                    f"({doc.get('top_organ_agreement')})"
                ),
            }
        )
    lc = ARTIFACTS / "label_change_eval.json"
    if lc.exists():
        s = (json.loads(lc.read_text(encoding="utf-8")) or {}).get("summary") or {}
        if s.get("n_scored"):
            out["evaluations"].append(
                {
                    "name": "anticipating a dated FDA label change",
                    "metric": (
                        "predicted rank of the organ FDA was about to warn about, fit "
                        "only on data public before that date"
                    ),
                    # Lower is better here, alone among these rows. Left implicit it is
                    # actively misleading: 4.67 against a null of 7.50 reads as a loss in
                    # a column where every other entry is higher-is-better, when it is in
                    # fact the model's best-looking result.
                    "direction": "lower_is_better",
                    "model": s.get("mean_rank"),
                    "best_baseline": s.get("null_mean_rank"),
                    "n_events": s.get("n_scored"),
                    "p_value": s.get("p_value"),
                    "verdict": (
                        f"mean rank {s['mean_rank']:.2f} of 14 beats the null of "
                        f"{s['null_mean_rank']}, but with {s['n_scored']} scorable events "
                        f"p = {s['p_value']:.3f}; at this sample size only "
                        f"{s.get('min_hits_for_significance')} of {s['n_scored']} could "
                        "have reached p<0.05. A case series, not a validation study."
                    ),
                }
            )
    hf = ARTIFACTS / "hard_flag_necessity.json"
    if hf.exists():
        doc = json.loads(hf.read_text(encoding="utf-8"))
        out["evaluations"].append(
            {
                "name": "how much of the output is the label-rule layer, not the fit",
                "metric": "label rules whose removal would change the band",
                # A count, not a score. Rendering it as 3.000 beside a column of AUCs
                # invites it to be read as one.
                "direction": "count",
                "model": doc.get("n_load_bearing"),
                "n_flags": doc.get("n_flags"),
                "verdict": (
                    f"{doc.get('n_load_bearing')} of {doc.get('n_flags')} label rules are "
                    "load-bearing, so those bands are not model results. The two that are "
                    "confirmatory are both deruxtecan/pulmonary."
                ),
            }
        )
    out["summary"] = (
        "Treat the ordering as weak evidence. The model loses to a base-rate baseline on "
        "within-arm axis ranking, sits at chance on across-agent discrimination, and does "
        "not separate from the baseline on agreement with approved dose-modification "
        "orderings once the interval is taken into account. Candidates sharing a rank are "
        "not distinguishable at all."
    )
    return out


LIMITATIONS = [
    "Research prototype. Not validated prospectively and not for use in patient care.",
    "The forward model does not beat a global-axis-mean baseline on within-arm axis "
    "ranking; see docs/MODEL_CARD.md before reading any number as predictive.",
    "Design features are agent-level constants, so 16 agents x 14 axes = 224 cells "
    "identify the design coefficients, not the 3,990 arm-axis cells.",
    "Only Tier 1 novelty is supported: a new combination of individually precedented "
    "parts. A new molecule in a known family is not supported.",
    "No efficacy model is used. Rankings are about predicted toxicity only.",
    "The comorbidity weighting is an elicited prior with zero training rows, derived "
    "from quantitative thresholds in trial exclusion criteria.",
    "Two of six payload mechanisms have enough agents to serve as a held-out fold.",
    "Organ risks come from two event tables that rank organs differently. An axis a "
    "declared comorbidity touches is banded on serious events, the rest on any-grade "
    "events, and each row states its basis. Bands are not comparable across bases: the "
    "serious scale is roughly ten times smaller, and each table's band edges are "
    "measured from that table.",
    "The one anticipatory evaluation -- did the model rank an organ highly before FDA "
    "added a warning for it -- is a case series of 3 scorable events, not a validation "
    "study, and does not reach significance.",
]

app = FastAPI(
    title="ADCTox",
    description=(
        "Research prototype: proposes ADC designs and estimates organ-system toxicity. "
        "Not a clinical decision tool."
    ),
    version="0.1.0",
)


@lru_cache(maxsize=1)
def _posterior() -> Posterior:
    path = ARTIFACTS / "posterior_other.npz"
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "No fitted posterior. Run `make forward` or "
                "`python scripts/propose_demo.py` to produce artifacts/posterior_other.npz."
            ),
        )
    return Posterior.load(path)


@lru_cache(maxsize=1)
def _registry() -> dict:
    import yaml

    path = ROOT / "conf" / "adc_registry.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["agents"]


def _reference_adcs(payload: str, family: str, mechanism: str) -> list[dict]:
    """Corpus agents that speak to this design, nearest relation first.

    `nearest_reference_adcs` was declared in the schema and returned empty by every code
    path, so a caller asking what the estimate rests on got an empty list and no way to
    tell that from "nothing is comparable". It matters most for a payload no agent
    carries: exatecan's estimate is the camptothecin/topoisomerase-I effect, and the
    reader should be able to see that no exatecan arm exists.
    """
    out = []
    for name, spec in _registry().items():
        if spec.get("payload") == payload:
            rel = "same payload"
        elif spec.get("payload_family") == family:
            rel = "same payload family"
        elif spec.get("mechanism") == mechanism:
            rel = "same mechanism"
        else:
            continue
        out.append({
            "agent": name, "relation": rel,
            "payload": spec.get("payload"), "linker": spec.get("linker"),
            "dar": spec.get("dar"), "target": spec.get("target"),
        })
    order = {"same payload": 0, "same payload family": 1, "same mechanism": 2}
    out.sort(key=lambda r: (order[r["relation"]], r["agent"]))
    return out[:6]


@lru_cache(maxsize=1)
def _serious_posterior() -> Posterior | None:
    """The serious-event fit, if it has been built.

    Optional rather than required, and the endpoints say which table each number came
    from, so a deployment without it degrades to the common table instead of failing.
    But it is what makes a comorbidity question answerable: measured on this corpus the
    two tables rank organs differently, and the serious one is the table that puts
    T-DXd's boxed-warning organ near the top instead of 10th of 14.
    """
    path = ARTIFACTS / "posterior_serious.npz"
    if not path.exists():
        return None
    return Posterior.load(path)


@lru_cache(maxsize=1)
def _version_info() -> dict:
    metrics = ARTIFACTS / "forward_other_metrics.json"
    corpus = "unknown"
    gate = None
    if metrics.exists():
        doc = json.loads(metrics.read_text(encoding="utf-8"))
        corpus = doc.get("corpus", "unknown")
        gate = doc.get("gate")
    return {"app": app.version, "corpus": corpus, "gate": gate}


# Served from the same process as the API: one artefact, one port, no CORS. The plan's
# week-1 fallback from a React build, taken deliberately -- with the model result negative,
# the report earns more than frontend tooling does.
_WEB = ROOT / "web"
if (_WEB / "index.html").exists():
    from fastapi.responses import FileResponse

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_WEB / "index.html")


@app.get("/api/v1/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/v1/version")
def version() -> dict:
    return _version_info()


@app.get("/api/v1/ranking-evidence")
def ranking_evidence() -> dict:
    """What the ranking is worth, measured. Served separately as well as inline."""
    return _ranking_evidence()


@app.get("/api/v1/disclaimer")
def disclaimer() -> dict:
    return {**Disclaimer().model_dump(), "limitations": LIMITATIONS}


@lru_cache(maxsize=1)
def _targets() -> list[dict]:
    """Registry targets, with the label a clinician would recognise.

    `target_label` is the common name -- CD30 for TNFRSF8 -- and the registry carries both
    because the gene symbol is what the corpus keys on and the label is what a reader knows.
    """
    seen: dict[str, dict] = {}
    for spec in _registry().values():
        gene = spec.get("target")
        if not gene:
            continue
        row = seen.setdefault(gene, {
            "id": gene,
            "label": spec.get("target_label") or gene,
            "n_adcs": 0,
        })
        row["n_adcs"] += 1
    return [seen[k] for k in sorted(seen)]


@app.get("/api/v1/model-card")
def model_card() -> PlainTextResponse:
    """The model card, served as written.

    The plan listed this endpoint and it was never built, which left the one document that
    opens with "the model does not beat a base-rate baseline on any of six evaluations"
    reachable only by reading the repository. Everything else about this API is arranged so
    a caller cannot take a number without its caveats; the caveats themselves should not be
    the part that requires a checkout.

    Served verbatim rather than summarised, because a summary of a limitations document is
    the thing a limitations document exists to prevent.
    """
    path = ROOT / "docs" / "MODEL_CARD.md"
    if not path.exists():
        raise HTTPException(status_code=503, detail="model card is not in this deployment")
    return PlainTextResponse(
        path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"X-Corpus-Version": _version_info()["corpus"][:200]},
    )


@app.get("/api/v1/ontology")
def ontology() -> dict:
    """Everything a client needs so it never hardcodes a list of its own."""
    # Shared read-only singleton; see default_taxonomy() on why builders do not use it.
    tax = default_taxonomy()
    space = DesignSpace()
    # The validated loader. This endpoint is what a client builds its UI from, so serving
    # it from a third independent parse of the CSV meant the axis-name validation
    # protected two readers and not this one -- the one whose output a user sees.
    rows = [
        {
            "id": row["id"], "label": row["label"],
            "organ_axes": list(row["organ_axes"]),
            "severity": row["severity"],
            "severity_basis": row["severity_basis"],
        }
        for row in comorbidity_registry().values()
    ]
    from ..design.constraints import ConstraintEngine

    return {
        "organ_axes": [{"id": a, "label": tax.axes[a]} for a in tax.axis_order],
        # Which constraints this build can evaluate, and why not where not. A constraint
        # that cannot fire is indistinguishable from one that fires and passes, and the
        # difference decides how much the screen is worth.
        "constraints": ConstraintEngine().active_constraints(),
        "comorbidities": rows,
        # Targets with clinical precedent, from the registry. The page used to hold a
        # literal array of fourteen of them under a comment claiming it hardcoded no list,
        # which hid ten of the registry's targets from the interface -- and the guard around
        # that array keyed off the comorbidity count, so it would have shown the hardcoded
        # targets even if this endpoint had served none.
        #
        # `n_adcs` is how many registry agents target it, which is the one fact about a
        # target this system can act on -- it sizes the comparison set behind the
        # nearest-real-ADC sentence. An earlier draft of this field said `in_corpus`, which
        # was true for all 24 of them and so said nothing.
        "targets": _targets(),
        "payloads": sorted(space.payloads),
        "linkers": sorted(space.linkers),
        "conjugations": sorted(space.conj_dar),
        "dar_hard_cap": space.dar_cap,
        "excluded_design_slots": {
            "fc_engineering": (
                "Not offered. No approved ADC uses it, no training arm carries it, and "
                "the primary literature on the mechanism it would target is mutually "
                "contradictory."
            )
        },
    }


@app.post("/api/v1/propose")
def propose_endpoint(req: ProposeRequest) -> JSONResponse:
    try:
        result = propose(
            target_antigen=req.target_antigen,
            condition_ids=req.comorbidity_profile.condition_ids,
            posterior=_posterior(),
            top_k=req.top_k,
            serious_posterior=_serious_posterior(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(
        {
            **result,
            "model_version": app.version,
            "corpus_version": _version_info()["corpus"],
            "disclaimer": Disclaimer().model_dump(),
            "limitations": LIMITATIONS,
            "interpretation": "relative_ranking_only",
            "ranking_evidence": _ranking_evidence(),
        }
    )


@app.post("/api/v1/assess")
def assess_endpoint(req: AssessRequest) -> JSONResponse:
    """Expert mode: score one fully specified design."""
    from ..design.enumerate import Design
    from ..comorbidity.exclusion_prior import driver as exclusion_driver
    from ..comorbidity.hard_flags import applicable as applicable_flags
    from ..comorbidity.hard_flags import override_band
    from ..model.comparator import axis_comparator
    from ..model.predict import (
        MIN_ARMS_FOR_A_BAND,
        decompose,
        decompose_summary,
        predict_draws,
        risk_band,
    )
    from ..pipeline import _FAMILY_OF

    space = DesignSpace()
    # Shared read-only singleton; see default_taxonomy() on why builders do not use it.
    tax = default_taxonomy()
    axes = list(tax.axis_order)
    d = req.design
    if d.payload not in space.payloads:
        raise HTTPException(422, f"unknown payload {d.payload!r}")
    if d.linker not in space.linkers:
        raise HTTPException(422, f"unknown linker {d.linker!r}")
    payload = space.payloads[d.payload]
    linker = space.linkers[d.linker]
    if linker["handle"] != payload["handle"]:
        raise HTTPException(
            422,
            f"linker {d.linker} expects a {linker['handle']} attachment handle and "
            f"{d.payload} presents {payload['handle']}; this combination is not chemically valid",
        )

    design = Design(
        target=d.target_antigen, payload=d.payload, mechanism=payload["mechanism"],
        linker=d.linker, cleavable=bool(linker["cleavable"]),
        conjugation=d.conjugation.value, dar=float(d.dar),
        isotype=d.isotype.value, masking=d.masking.value,
    )
    post = _posterior()
    family = _FAMILY_OF.get(d.payload, "")
    if design.mechanism not in post.mechanisms:
        # Tier 3: the model has no coefficient for this mechanism and must refuse rather
        # than extrapolate. No point estimate is returned.
        return JSONResponse(
            {
                "assessment_id": f"asm_{uuid.uuid4().hex[:12]}",
                "coverage": {
                    "novelty_tier": 3, "in_distribution": False,
                    "nearest_reference_adcs": [],
                    "warnings": [
                        f"payload mechanism {design.mechanism!r} is absent from the "
                        "training corpus; no point estimate is defensible"
                    ],
                },
                "organ_risks": [], "disclaimer": Disclaimer().model_dump(),
                "limitations": LIMITATIONS,
                "interpretation": "relative_ranking_only",
            }
        )

    draws = predict_draws(
        post, mechanisms=[design.mechanism], families=[family],
        dars=np.array([design.dar]),
        cleavables=np.array([float(design.cleavable)]),
    )
    comorb = resolve_comorbidities(req.comorbidity_profile.condition_ids)
    rates = draws[:, 0, :]
    mi = post.mechanisms.index(design.mechanism)

    # The serious-event view of the same design. An axis the patient is vulnerable on is
    # a serious-harm question, so that axis is banded here rather than on the common
    # table, where the same chemistry can sit in the bottom third.
    spost = _serious_posterior()
    srates = smi = None
    if spost is not None and design.mechanism in spost.mechanisms:
        sdraws = predict_draws(
            spost, mechanisms=[design.mechanism], families=[family],
            dars=np.array([design.dar]),
            cleavables=np.array([float(design.cleavable)]),
        )
        srates = sdraws[:, 0, :]
        smi = spost.mechanisms.index(design.mechanism)

    def serious_cell(axis: str) -> tuple[float | None, int]:
        if srates is None or axis not in spost.axes:
            return (None, 0)
        j = spost.axes.index(axis)
        return (float(srates[:, j].mean()), int(spost.evidence_arms[smi, j]))

    def serious_band(axis: str) -> dict | None:
        """The serious rate's credible interval. Every number carries one."""
        if srates is None or axis not in spost.axes:
            return None
        j = spost.axes.index(axis)
        return {
            "lo": round(float(np.percentile(srates[:, j], 5)), 4),
            "hi": round(float(np.percentile(srates[:, j], 95)), 4),
            "kind": "credible_90",
        }

    organ_risks = []
    for i, axis in enumerate(axes):
        mean = float(rates[:, i].mean())
        n_arms = int(post.evidence_arms[mi, i])
        s_mean, s_arms = serious_cell(axis)
        use_serious = s_mean is not None and axis in comorb.at_risk_axes
        band_basis = "serious" if use_serious else "common"
        # Reported evidence follows the basis, so the count supports the figure banded.
        shown_arms = s_arms if use_serious else n_arms
        n_agents = int(post.evidence_agents[mi, i])
        axis_flags = applicable_flags(
            design.mechanism, design.payload,
            set(req.comorbidity_profile.condition_ids),
        ).get(axis, [])
        # A label rule can raise a band but never lower one, including over
        # `no_evidence`: a regulator's warning is evidence, and an organ named in a boxed
        # warning must not render as unstudied.
        band = override_band(
            risk_band(s_mean, s_arms, spost.band_edges) if use_serious
            else risk_band(mean, n_arms, post.band_edges),
            axis_flags,
        )
        weight = 1.0 + 2.0 * comorb.severity_by_axis.get(axis, 0.0)
        drivers = decompose(post, design.mechanism, family, design.dar,
                            design.cleavable, axis)
        for f in axis_flags:
            drivers.append(f.as_driver())
        # The expert-prior view of the same question, kept apart from the fitted terms
        # because the two are negatively coupled -- excluding patients with disease in an
        # organ suppresses the observed rate there.
        excl = exclusion_driver(design.mechanism, axis)
        if excl is not None:
            drivers.append(excl)
        if axis in comorb.at_risk_axes:
            # Kept in the same list but marked, because a reader has to be able to see
            # that this term is a declared weight and not a fitted effect.
            drivers.append(
                {
                    "factor": f"comorbidity weighting on {axis}",
                    "detail": "multiplies the objective, does not change the estimate",
                    "source": "elicited_prior",
                    "contribution": round(weight, 4),
                }
            )
        organ_risks.append(
            {
                "organ_axis": axis, "label": tax.axes[axis],
                # Withheld where the corpus has too little to say; see MIN_ARMS_FOR_A_BAND.
                "point_estimate": round(mean, 4) if n_arms >= MIN_ARMS_FOR_A_BAND else None,
                "interval": {
                    "lo": round(float(np.percentile(rates[:, i], 5)), 4),
                    "hi": round(float(np.percentile(rates[:, i], 95)), 4),
                    "kind": "credible_90",
                },
                "serious_estimate": (
                    round(s_mean, 4)
                    if s_mean is not None and s_arms >= MIN_ARMS_FOR_A_BAND
                    else None
                ),
                "serious_interval": (
                    serious_band(axis)
                    if s_mean is not None and s_arms >= MIN_ARMS_FOR_A_BAND
                    else None
                ),
                "risk_band": band,
                # Which event table the band was computed on, and therefore which
                # question it answers. Not comparable across bases: serious rates are an
                # order of magnitude smaller, and each table has its own measured edges.
                "band_basis": band_basis,
                "band_source": "rule" if axis_flags else "model",
                # Follows the band basis: the count has to support the figure banded.
                "n_supporting_agents": (
                    int(spost.evidence_agents[smi, spost.axes.index(axis)])
                    if use_serious else n_agents
                ),
                "n_supporting_arms": shown_arms,
                # Where this rate sits among the chemistries that have actually been built.
                # A rate on its own is close to unreadable, and the plan asked for an
                # ordinal position with its denominator rather than a percentile, which on
                # a sample of this size would invent resolution. Computed on the table the
                # band was computed on, or the question and the comparison would disagree.
                "comparator": axis_comparator(
                    spost if use_serious else post,
                    axis,
                    s_mean if use_serious and s_mean is not None else mean,
                ),
                "weight_applied": weight,
                "at_risk_for_patient": axis in comorb.at_risk_axes,
                "drivers": drivers,
                "driver_sum": decompose_summary(
                    [d for d in drivers if d["source"] == "model"], mean
                ),
            }
        )
    return JSONResponse(
        {
            "assessment_id": f"asm_{uuid.uuid4().hex[:12]}",
            "model_version": app.version,
            "corpus_version": _version_info()["corpus"],
            "organ_risks": organ_risks,
            "comorbidity_resolution": comorb.per_condition,
            "coverage": _coverage(design, family, post),
            "disclaimer": Disclaimer().model_dump(),
            "limitations": LIMITATIONS,
            "interpretation": "relative_ranking_only",
        }
    )
