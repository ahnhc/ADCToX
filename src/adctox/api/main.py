"""FastAPI app. The scope constraint is carried in the payload, not only in the UI.

Every response embeds the disclaimer and the limitations list, so bypassing the frontend
does not bypass the framing. Nothing is persisted: the ids in responses are correlation
handles, not record locators.
"""

from __future__ import annotations

import csv
import json
import uuid
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from ..design.enumerate import DesignSpace
from ..model.predict import Posterior
from ..pipeline import propose, resolve_comorbidities
from ..schemas import AssessRequest, Disclaimer, ProposeRequest
from ..taxonomy import Taxonomy

ROOT = Path(__file__).resolve().parents[3]
CONF = ROOT / "conf"
ARTIFACTS = ROOT / "artifacts"

@lru_cache(maxsize=1)
def _ranking_evidence() -> dict:
    """What the ordering is actually worth, measured, served with every ranking.

    Three evaluations, and they do not agree, so all three travel with the output:
    the model loses to a base-rate baseline on within-arm axis ranking, sits at chance on
    across-agent discrimination, and wins marginally on agreement with the dose-modification
    orderings in approved labels. A caller who sees only the ranking would read far more
    into it than that.
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
                    "model": res.get("macro_auc"),
                    "best_baseline": max(
                        res.get("macro_auc_mech_baseline") or 0,
                        res.get("macro_auc_global_baseline") or 0,
                    ),
                    "delta": res.get("delta_auc_mean"),
                    "delta_ci": res.get("delta_auc_ci"),
                    "verdict": "model loses to the baseline",
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
                        "model": None,
                        "verdict": f"not applicable -- {aas.get('reason', '')}",
                    }
                )
            elif aas.get("model_mean") is not None:
                out["evaluations"].append(
                    {
                        "name": f"across-agent per-axis discrimination, {split}",
                        "metric": "mean Spearman across agents within an axis",
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
                "model": doc.get("mean_rho_model"),
                "best_baseline": max(
                    doc.get("mean_rho_mech_baseline") or 0,
                    doc.get("mean_rho_global_baseline") or 0,
                ),
                "delta": doc.get("paired_delta_vs_best_baseline"),
                "delta_ci": doc.get("paired_delta_ci"),
                "top_organ_agreement": doc.get("top_organ_agreement"),
                "verdict": (
                    "model beats the baseline, but only marginally, and it is at chance "
                    "on naming the organ the label fears most"
                ),
            }
        )
    out["summary"] = (
        "Treat the ordering as weak evidence. The model loses to a base-rate baseline on "
        "within-arm axis ranking, sits at chance on across-agent discrimination, and beats "
        "the baseline only marginally on agreement with approved dose-modification "
        "orderings. Candidates sharing a rank are not distinguishable at all."
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


@app.get("/api/v1/ontology")
def ontology() -> dict:
    """Everything a client needs so it never hardcodes a list of its own."""
    tax = Taxonomy()
    space = DesignSpace()
    rows = []
    with (CONF / "comorbidity_registry.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(
                {
                    "id": row["id"], "label": row["label"],
                    "organ_axes": [a for a in row["organ_axes"].split(";") if a],
                    "severity": float(row["severity"]),
                    "severity_basis": row["severity_basis"],
                }
            )
    return {
        "organ_axes": [{"id": a, "label": tax.axes[a]} for a in tax.axis_order],
        "comorbidities": rows,
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
    from ..model.predict import (
        MIN_ARMS_FOR_A_BAND,
        decompose,
        decompose_summary,
        predict_draws,
        risk_band,
    )
    from ..pipeline import _FAMILY_OF

    space = DesignSpace()
    tax = Taxonomy()
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

    organ_risks = []
    for i, axis in enumerate(axes):
        mean = float(rates[:, i].mean())
        n_arms = int(post.evidence_arms[mi, i])
        s_mean, s_arms = serious_cell(axis)
        use_serious = s_mean is not None and axis in comorb.at_risk_axes
        band_basis = "serious" if use_serious else "common"
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
                "risk_band": band,
                # Which event table the band was computed on, and therefore which
                # question it answers. Not comparable across bases: serious rates are an
                # order of magnitude smaller, and each table has its own measured edges.
                "band_basis": band_basis,
                "band_source": "rule" if axis_flags else "model",
                "n_supporting_agents": n_agents,
                "n_supporting_arms": n_arms,
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
            "coverage": {
                "novelty_tier": 1 if family in post.families else 2,
                "in_distribution": family in post.families,
                "nearest_reference_adcs": [],
                "warnings": (
                    []
                    if family in post.families
                    else [
                        f"payload family {family!r} is absent from the training corpus; "
                        "the estimate falls back to its mechanism"
                    ]
                ),
            },
            "disclaimer": Disclaimer().model_dump(),
            "limitations": LIMITATIONS,
            "interpretation": "relative_ranking_only",
        }
    )
