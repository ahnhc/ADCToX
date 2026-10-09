"""Tests for the evidence floor and the constraint that stops it being gamed.

These cover a chain of three faults, each exposed by fixing the one before it:

1. `risk_band`'s `no_evidence` state was unreachable because every caller passed a
   hardcoded arm count of 1. The state was documented, enforced in the markup and
   impossible to trigger.
2. With real counts wired in, the top-ranked candidate for an interstitial-lung-disease
   profile turned out to have **one** supporting arm on the pulmonary axis.
3. Which exposed the real fault: minimising weighted risk rewards ignorance, because an
   unevidenced axis falls back to a prior-driven estimate that is often low, so the
   least-studied chemistry wins.
"""

from __future__ import annotations

import numpy as np

from adctox.design.constraints import ConstraintEngine
from adctox.design.enumerate import Design, DesignSpace
from adctox.model.predict import (
    MIN_ARMS_FOR_A_BAND,
    Posterior,
    decompose,
    decompose_summary,
    risk_band,
)

AXES = ["hepatic", "pulmonary", "haematologic"]


# The measured otherEvents edges (15th/60th percentile of non-zero observed rates).
EDGES = (0.0645, 0.2174)


def _design(payload="DXd", linker="GGFG", mechanism="topo1", dar=8.0, cleavable=True):
    return Design(
        target="ERBB2", payload=payload, mechanism=mechanism, linker=linker,
        cleavable=cleavable, conjugation="interchain_cysteine", dar=dar,
        isotype="IgG1", masking="none",
    )


def test_no_evidence_band_is_reachable() -> None:
    """The state has to fire below the floor and not fire above it."""
    assert risk_band(0.01, 0, EDGES) == "no_evidence"
    assert risk_band(0.01, MIN_ARMS_FOR_A_BAND - 1, EDGES) == "no_evidence"
    assert risk_band(0.01, MIN_ARMS_FOR_A_BAND, EDGES) == "low"


def test_no_evidence_is_not_low_risk() -> None:
    """A thin axis and a genuinely low-risk axis must not land in the same band, because
    in a colour scale they would be indistinguishable and they mean opposite things."""
    assert risk_band(0.004, 1, EDGES) != risk_band(0.004, 40, EDGES)


def test_c6_blocks_a_candidate_with_no_evidence_on_an_at_risk_axis() -> None:
    """Observed in the real output: a duocarmazine design with one supporting pulmonary
    arm took rank 1 for an ILD profile. Ranking it against evidenced chemistry treats
    "unstudied" as "safe"."""
    engine = ConstraintEngine()
    design = _design(payload="seco-DUBA", linker="val_cit_cleavable",
                     mechanism="dna_alkyl", dar=2.0)
    thin = {"pulmonary": 1, "hepatic": 1, "haematologic": 2}
    blocked = engine.check(design, at_risk_axes={"pulmonary"}, evidence_arms=thin)
    assert not blocked.passed
    assert any("C6" in f for f in blocked.failures)
    # The same design is admissible when the patient has no vulnerability there.
    allowed = engine.check(design, at_risk_axes=set(), evidence_arms=thin)
    assert all("C6" not in f for f in allowed.failures)


def test_c6_passes_when_the_at_risk_axis_is_well_evidenced() -> None:
    engine = ConstraintEngine()
    rich = {"pulmonary": 33, "hepatic": 31, "haematologic": 36}
    res = engine.check(_design(), at_risk_axes={"pulmonary"}, evidence_arms=rich)
    assert all("C6" not in f for f in res.failures)


def test_c6_is_inert_without_evidence_data() -> None:
    """Callers that do not supply counts must not get a silent pass *or* a silent block;
    the check simply does not apply."""
    engine = ConstraintEngine()
    res = engine.check(_design(), at_risk_axes={"pulmonary"}, evidence_arms=None)
    assert all("C6" not in f for f in res.failures)
    assert "C6_evidence_on_at_risk_axes" not in res.margins


def _posterior() -> Posterior:
    n = 40
    rng = np.random.default_rng(0)
    return Posterior(
        mu_axis=rng.normal(-2.0, 0.1, (n, 3)),
        mech_axis=rng.normal(0.0, 0.1, (n, 2, 3)),
        family_axis=rng.normal(0.0, 0.1, (n, 2, 3)),
        cleav_axis=rng.normal(0.0, 0.1, (n, 3)),
        b_dar=rng.normal(0.03, 0.01, n), b_combo=np.zeros(n),
        sigma_agent=np.full(n, 0.1),
        axes=AXES, mechanisms=["tubulin", "topo1"],
        families=["auristatin", "camptothecin"],
        dar_mean=4.0, cleavable_mean=0.875,
        # Passed explicitly, never defaulted: the band scale is a property of the event
        # table, and an implicit one is what made a 4% serious rate read "low".
        kind="other", band_edges=(0.0645, 0.2174),
        evidence_agents=np.array([[4, 4, 4], [3, 3, 3]], dtype=np.int32),
        evidence_arms=np.array([[40, 38, 41], [22, 33, 20]], dtype=np.int32),
    )


def test_decomposition_is_exact_in_logit_space() -> None:
    """The model is linear in logit space, so this is a decomposition and not an
    attribution heuristic. Every term must be present and the total must be the sum."""
    post = _posterior()
    terms = decompose(post, "topo1", "camptothecin", 8.0, True, "pulmonary")
    assert len(terms) == 4  # baseline, chemistry, linker, DAR
    assert all(t["contribution"] is not None for t in terms)
    assert {t["source"] for t in terms} == {"model"}
    summary = decompose_summary(terms, reported_rate=0.14)
    assert abs(summary["logit_total"] - sum(t["contribution"] for t in terms)) < 1e-9


def test_decomposition_summary_states_the_jensen_gap() -> None:
    """The terms are posterior means in logit space, so sigmoid(sum) is not exactly the
    mean rate. The summary must expose that rather than let a caller assume it away."""
    post = _posterior()
    terms = decompose(post, "topo1", "camptothecin", 8.0, True, "pulmonary")
    summary = decompose_summary(terms, reported_rate=0.1394)
    assert "gap" in summary and abs(summary["gap"]) < 0.05
    assert "Jensen" in summary["note"]


def test_decomposition_does_not_double_count_the_mechanism() -> None:
    """Family carries its mechanism through the nesting, so listing both would add the
    mechanism effect twice."""
    post = _posterior()
    terms = decompose(post, "topo1", "camptothecin", 8.0, True, "pulmonary")
    factors = " ".join(t["factor"] for t in terms)
    assert "payload chemistry" in factors
    assert "payload mechanism" not in factors


def test_unknown_family_falls_back_to_its_mechanism() -> None:
    post = _posterior()
    terms = decompose(post, "topo1", "not-a-family", 8.0, True, "pulmonary")
    factors = " ".join(t["factor"] for t in terms)
    assert "payload mechanism" in factors


def test_delivered_dose_floor_is_computed_not_asserted() -> None:
    """The floor is the 10th percentile over approved ADCs, so there is no constant to
    argue about -- and it must actually exclude something."""
    engine = ConstraintEngine()
    assert engine.n_reference_adcs >= 10
    assert engine.delivered_dose_floor > 0
    space = DesignSpace()
    designs, _ = space.enumerate("ERBB2")
    failed = [d for d in designs if not engine.check(d).passed]
    assert failed, "a floor that excludes nothing is not a constraint"


def test_constraint_status_is_declared_and_honest() -> None:
    """A constraint that cannot fire must say so.

    C3 is fully implemented and never evaluated: no expression data is ingested, so
    `selectivity` is None at every call site. The parameter is threaded through three
    layers of signature and DATA_SOURCES.md listed HPA/GTEx as an attributed source for
    it, so nothing indicated the screen was inert. This project has already shipped four
    things of this shape -- a dead API option, an always-empty reference list and two
    driver sources no code path emitted -- which is why the status is now asserted.
    """
    from adctox.design.constraints import ConstraintEngine

    status = ConstraintEngine().active_constraints()
    assert set(status) == {
        "C1_payload_potency", "C2_delivered_dose", "C3_selectivity",
        "C4_tier_1_precedent", "C5_chemistry_validity", "C6_evidence_on_at_risk_axes",
    }
    # C3 is now active as a band-raising flag and still not a rejection path. The
    # distinction is the point: expression does not predict labelled organ toxicity in
    # aggregate (AUROC 0.52-0.58 over 14 approved ADCs), so rejecting a candidate on it
    # would outrun the evidence, while locating the organ a target could reach is
    # supported by 5 of 5 textbook cases.
    assert "FLAG, NOT A REJECTION" in status["C3_selectivity"].upper(), (
        status["C3_selectivity"]
    )
    for name, text in status.items():
        if name != "C3_selectivity":
            assert text.startswith("active"), (name, text)


def test_nothing_supplies_selectivity_so_c3_cannot_fire() -> None:
    """Pins the reason C3 is reported inactive, rather than trusting the label.

    If a caller starts passing selectivity, this fails and the status string above has to
    be revisited -- which is the point.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src"
    callers = []
    for path in root.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            # an argument being *passed*, not declared or forwarded as None
            if re.search(r"selectivity\s*=\s*(?!None)(?!selectivity\b)\w", line):
                callers.append(f"{path.name}: {line.strip()}")
    assert not callers, (
        "something now supplies a selectivity value, so C3 can fire:\n  "
        + "\n  ".join(callers)
    )


def test_the_waterfall_sums_to_the_rate_across_a_sweep() -> None:
    """The decomposition's honesty, measured rather than argued.

    `driver_sum` reports the gap between the model terms' sum and the rate the row shows,
    with a note saying the difference is Jensen's inequality: the terms are posterior means
    in logit space, so they decompose the mean logit exactly and the mean rate only
    approximately. That note is only acceptable if the gap is small, and "small" was never
    measured.

    Over six payload chemistries by four comorbidity profiles -- 336 rows -- the largest
    absolute gap is 0.0128 and the median 0.0054. Those were 0.0047 and 0.0012 on the
    16-agent corpus; the gap grew because it scales with the posterior variance, and
    `sigma_agent` went from 0.159 to 0.343 when the corpus was rebuilt.

    The bound alone would be arbitrary -- raising it to fit whatever the last refit produced
    is fitting the test to the data -- so the sign is checked too, and that is what
    distinguishes Jensen from a missing term. The sigmoid is convex below 0.5, so there the
    mean rate exceeds the rate implied by the mean logit and the gap is negative; above 0.5
    it flips. Measured: negative in 156 of 165 cells below 0.5 and positive in 3 of 3 above.
    A term in the model and absent from the decomposition would shift every cell the same
    way regardless of where its rate sits.
    """
    import numpy as np
    from fastapi.testclient import TestClient

    from adctox.api.main import app

    client = TestClient(app)
    designs = [
        ("DXd", "GGFG", "interchain_cysteine", 8.0),
        ("MMAE", "vc_PABC", "interchain_cysteine", 4.0),
        ("DM1", "SMCC", "lysine", 3.5),
        ("MMAF", "mc", "interchain_cysteine", 4.0),
        ("SG3199", "val_ala_PABC_PEG8", "interchain_cysteine", 2.0),
        ("DGN549", "SMCC", "lysine", 2.0),
    ]
    profiles = [
        [], ["cirrhosis"],
        ["ckd_stage_4_5", "interstitial_lung_disease"], ["severe_psoriasis"],
    ]
    gaps, signed = [], []
    for payload, linker, conj, dar in designs:
        for conditions in profiles:
            r = client.post("/api/v1/assess", json={
                "design": {
                    "target_antigen": "ERBB2", "payload": payload, "linker": linker,
                    "conjugation": conj, "dar": dar,
                    "isotype": "IgG1", "masking": "none",
                },
                "comorbidity_profile": {"conditions": conditions},
            })
            if r.status_code != 200:
                continue
            for row in r.json().get("organ_risks", []):
                summary = row.get("driver_sum") or {}
                if summary.get("gap") is None:
                    continue
                gaps.append(abs(summary["gap"]))
                if row.get("point_estimate") is not None:
                    signed.append((row["point_estimate"], summary["gap"]))

    assert len(gaps) > 300, len(gaps)
    worst = float(np.max(gaps))
    assert worst < 0.02, (
        f"the driver waterfall misses {worst:.4f} of the rate at worst, which is more than "
        "Jensen's inequality accounts for at this posterior width"
    )
    # The sign test, which is what makes the bound above a bound and not an accommodation.
    below = [g for rate, g in signed if rate < 0.5]
    assert len(below) > 100, len(below)
    negative = sum(1 for g in below if g < 0)
    assert negative / len(below) > 0.85, (
        f"only {negative} of {len(below)} gaps below rate 0.5 are negative; Jensen's "
        "inequality makes them negative there, so a two-sided pattern means a term is in "
        "the model and not in the decomposition"
    )
