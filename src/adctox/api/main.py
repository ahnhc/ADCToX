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
            include_tier_1_5=req.include_tier_1_5,
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
        }
    )


@app.post("/api/v1/assess")
def assess_endpoint(req: AssessRequest) -> JSONResponse:
    """Expert mode: score one fully specified design."""
    from ..design.enumerate import Design
    from ..model.predict import predict_draws, risk_band
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
    organ_risks = []
    for i, axis in enumerate(axes):
        mean = float(rates[:, i].mean())
        organ_risks.append(
            {
                "organ_axis": axis, "label": tax.axes[axis],
                "point_estimate": round(mean, 4),
                "interval": {
                    "lo": round(float(np.percentile(rates[:, i], 5)), 4),
                    "hi": round(float(np.percentile(rates[:, i], 95)), 4),
                    "kind": "credible_90",
                },
                "risk_band": risk_band(mean, 1),
                "weight_applied": 1.0 + 2.0 * comorb.severity_by_axis.get(axis, 0.0),
                "at_risk_for_patient": axis in comorb.at_risk_axes,
                "drivers": [
                    {"factor": f"payload_mechanism={design.mechanism}",
                     "source": "model", "contribution": None},
                    {"factor": f"linker_cleavable={design.cleavable}",
                     "source": "model", "contribution": None},
                    {"factor": f"dar={design.dar}", "source": "model", "contribution": None},
                ]
                + (
                    [{"factor": f"comorbidity weighting on {axis}",
                      "source": "elicited_prior", "contribution": None}]
                    if axis in comorb.at_risk_axes else []
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
