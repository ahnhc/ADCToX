#!/usr/bin/env python
"""Regenerate the report's fitted-parameter block from the metrics artefact.

Why this exists: the report quoted `tau_mech` 0.592 [0.503, 0.711] in "What the model does
support" while the artefact said 0.5816 [0.4926, 0.6863], and quoted the same 0.592
elsewhere as a *pre-fix* value -- so the report contradicted itself about one number. Three
parameters were stale the same way. The guard that should have caught it, check_report.py,
was passing 99% of fabricated figures.

Typing these by hand loses every time a model is refit, and refits are frequent here. So
the numbers come from the artefact and the prose stays in this file, next to the parameter
it interprets. Run it after `make forward`; `make check-report` depends on it.

The interpretations are deliberately kept here rather than in the markdown: an
interpretation that outlives its number is the same bug in prose form, and keeping them
together means a sign flip forces the sentence to be rewritten.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from collections.abc import Callable
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import residual_scale as _residual_scale

BEGIN = "<!-- generated: fitted-parameters -->"
END = "<!-- /generated: fitted-parameters -->"

# The censoring sensitivity table moves with Monte Carlo noise on every rerun -- three of
# its six figures were stale after one -- so it is generated too.
CENS_BEGIN = "<!-- generated: censoring-sensitivity -->"
CENS_END = "<!-- /generated: censoring-sensitivity -->"
FD_BEGIN = "<!-- generated: fold-difficulty -->"
FD_END = "<!-- /generated: fold-difficulty -->"

ENR_BEGIN = "<!-- generated: exclusion-enrichment -->"
ENR_END = "<!-- /generated: exclusion-enrichment -->"

HFN_BEGIN = "<!-- generated: hard-flag-necessity -->"
HFN_END = "<!-- /generated: hard-flag-necessity -->"

LCE_BEGIN = "<!-- generated: label-change -->"
LCE_END = "<!-- /generated: label-change -->"

RR_BEGIN = "<!-- generated: rank-resolution -->"
RR_END = "<!-- /generated: rank-resolution -->"

PAC_BEGIN = "<!-- generated: payload-compression -->"
PAC_END = "<!-- /generated: payload-compression -->"

SAX_BEGIN = "<!-- generated: source-axis -->"
SAX_END = "<!-- /generated: source-axis -->"

RES_BEGIN = "<!-- generated: results-table -->"
RES_END = "<!-- /generated: results-table -->"

CENS_ROWS = [
    ("censored", "censored"),
    ("zero_imputed", "zero-imputed"),
    ("threshold_0_only", "completely-reported subset only"),
]

def _relative_to_mech(cell: dict, metrics: dict) -> str:
    """Phrase one scale against `tau_mech`, from the numbers rather than from memory.

    "about half the size of the mechanism scale" was hand-written beside `tau_cleav`. It
    happened to be true. Nothing would have moved it if the fit had, which is the defect
    negative result 38 is about, so the fraction is read off instead of asserted.
    """
    tm = metrics.get("tau_mech", {}).get("mean")
    if not tm:
        return ""
    ratio = cell["mean"] / tm
    # Four decimals, so `check_report.py` has real power on the figure: its own measured
    # false-pass rate against fabricated numbers is 100% at two decimals and 31% at four.
    if ratio < 0.60:
        return f"about {ratio:.4f} times the mechanism scale"
    if ratio < 0.90:
        return f"{ratio:.4f} times the mechanism scale, not far below it"
    if ratio < 1.10:
        return f"{ratio:.4f} times the mechanism scale -- effectively the same size"
    return f"{ratio:.4f} times the mechanism scale, which it exceeds"


def _straddles_zero(cell: dict) -> bool:
    """Whether the 90% interval contains zero, which is the claim, not a recollection."""
    return cell["q05"] <= 0.0 <= cell["q95"]


def _tau_mech_note(metrics: dict) -> str | None:
    """"Supported by the data rather than asserted by a parameter count" is a sign claim.

    Section 4's conclusion -- that the design terms cannot reorder the organ ranking -- is
    argued from this scale clearing zero while being the largest of the design scales. Both
    halves are read off here rather than remembered, and every design scale in the block is
    in the comparison, not only the one that happens to be sampled today.
    """
    cell = metrics.get("tau_mech")
    if not cell or "q05" not in cell:
        return None
    if _straddles_zero(cell):
        return (
            "the mechanism x axis interaction, whose scale now includes zero -- so on this "
            "corpus it is asserted by the parameter count rather than supported by the "
            "data, and section 4's conclusion rests on it being the other way round."
        )
    others = [
        c["mean"] for name in ("tau_cleav", "tau_family")
        if isinstance((c := metrics.get(name)), dict) and c.get("mean")
    ]
    if others and cell["mean"] < max(others):
        return (
            "the mechanism x axis interaction clears zero, so it is supported by the data "
            "rather than asserted by a parameter count -- but it is no longer the largest "
            f"design scale in this block, which reaches {max(others):.4f}. Section 4 argues "
            "from the mechanism being the dominant design term, so that argument needs "
            "rechecking before it is quoted."
        )
    return (
        "the mechanism x axis interaction is supported by the data rather than asserted "
        "by a parameter count: the scale clears zero, and it is the largest of the design "
        "scales in this block."
    )


def _b_log_n_note(metrics: dict, sibling: dict | None) -> str | None:
    cell = metrics.get("coefficients", {}).get("b_log_n")
    if not cell:
        return None
    lead = (
        "an ascertainment effect that would have been attributed to the design had it not "
        "been controlled. "
    )
    there = (sibling or {}).get("coefficients", {}).get("b_log_n")
    if not there or not cell.get("mean"):
        return lead.rstrip()
    # The one coefficient whose sign is not shared by the two tables. Worth saying here
    # rather than only in the censoring comparison, because the sentence above reads as a
    # single mechanism and on this evidence it is not one.
    if (cell["mean"] > 0) != (there["mean"] > 0):
        return lead + (
            f"It takes the opposite sign on the seriousEvents table ({there['mean']:+.4f} "
            f"against {cell['mean']:+.4f} here), which is the largest disagreement between "
            "the two tables in this block, so what it absorbs is not one effect measured "
            "twice. Treat it as a per-table nuisance term and not as an estimate of how "
            "ascertainment works."
        )
    return lead + (
        f"The same sign on the seriousEvents table ({there['mean']:+.4f}), so the two "
        "tables agree about its direction."
    )


def _b_thresh_note(metrics: dict, sibling: dict | None) -> str | None:
    """"Four times larger on the seriousEvents table" is a ratio between two fitted values.

    It was hand-written, and it was the argument for calling this coefficient a reporting
    covariate rather than the censoring correction, so it is the last clause in this block
    that should have been a constant. Derived now from both tables; without the sibling
    artefact the comparison is omitted rather than asserted.
    """
    here = metrics.get("coefficients", {}).get("b_thresh")
    if not here:
        return None
    lead = "the reporting-threshold covariate. "
    there = (sibling or {}).get("coefficients", {}).get("b_thresh")
    if not there or not here.get("mean"):
        return lead + (
            "The comparison that makes it a reporting covariate rather than the censoring "
            "correction needs the other event table, whose metrics are absent here."
        )
    ratio = there["mean"] / here["mean"]
    # Same sign and larger there is the finding. A sign flip would be a different one, and
    # saying "N times larger" about it would hide that.
    if ratio < 0:
        return lead + (
            f"It takes the opposite sign on the seriousEvents table ({there['mean']:+.4f} "
            f"against {here['mean']:+.4f} here), which has no censored cells at all, so it "
            "is not estimating one thing on the two tables and should not be read as a "
            "censoring correction on either."
        )
    return lead + (
        f"Not the censoring correction: it is {ratio:.4f} times larger on the seriousEvents "
        "table, which has no censored cells at all, so it is substantially absorbing "
        "trial-level reporting practice."
    )


def _tau_cleav_note(metrics: dict) -> str | None:
    cell = metrics.get("tau_cleav")
    if not cell or "q05" not in cell:
        return None
    clear = "Clear of zero" if not _straddles_zero(cell) else "Includes zero"
    rel = _relative_to_mech(cell, metrics)
    direction = (
        "so linker cleavability shifts the organ profile, and shifts it less than the "
        "payload mechanism does"
        if cell["mean"] < metrics.get("tau_mech", {}).get("mean", float("inf"))
        else "so linker cleavability shifts the organ profile by more than the payload "
             "mechanism does, which would be a surprise worth checking before quoting"
    )
    return (
        "the scale of the cleavable-versus-non-cleavable linker contrast across axes. "
        f"{clear}, and {rel} -- {direction}. This is the one design axis the corpus "
        "identifies comfortably: cleavability is binary and needs only 8 agents to "
        "estimate, against the 40 a mechanism level needs and the 80 a payload level would."
    )


def _b_dar_note(metrics: dict) -> str | None:
    cell = metrics.get("coefficients", {}).get("b_dar")
    if not cell or "q05" not in cell:
        return None
    lead = (
        "includes zero. " if _straddles_zero(cell)
        else "clear of zero, which it was not on the registry corpus -- worth checking "
             "against the confounding below before it is quoted as a DAR effect. "
    )
    return lead + (
        "DAR is an agent-level constant and is confounded with agent identity here. The "
        "pharmacokinetic literature supports a DAR effect; this corpus does not resolve one."
    )


def _sigma_agent_note(metrics: dict) -> str | None:
    """Derive the reading rather than assert it.

    `sigma_agent` is the residual between-agent SD *after* the design slots; `tau_mech` is
    the scale of the mechanism x axis effect the slots supply. The ratio of the two decides
    whether the slots account for the between-agent variation, so the sentence is selected
    by that ratio and prints it. A hardcoded "small" survived the corpus rebuild that moved
    this parameter from 0.159 to 0.343 and became false; see negative result 38.

    The ratio and its bands come from `residual_scale.py`, which is where they are measured
    and where the artefact the report's figures are checked against is written. Computing
    them a second time here would be a second place to get them wrong.
    """
    got = _residual_scale._ratio(metrics)
    if not got:
        return None
    lead = (
        f"the residual between-agent scale left after the design slots, at {got['ratio']:.4f} "
        f"times the mechanism x axis scale (`tau_mech` {got['tau_mech']['mean']:.4f}). "
    )
    if got["ratio"] < _residual_scale.ACCOUNTS_FOR:
        return lead + (
            "Small against that scale, so the design slots account for much of the "
            "between-agent variation."
        )
    if got["ratio"] < _residual_scale.DOES_NOT_ACCOUNT_FOR:
        return lead + (
            "Comparable in magnitude, so the slots account for part of the between-agent "
            "variation and leave a residual of the same order as the mechanism effect "
            "itself. Agent identity carries information the seven design slots do not. On "
            "the seriousEvents table, which has no censored cells, the same ratio is above "
            "one and the reading reverses -- see `artifacts/residual_scale.json`."
        )
    return lead + (
        "At or above that scale, so the design slots do NOT account for the between-agent "
        "variation: what distinguishes two agents of the same mechanism, linker and DAR is "
        "larger than what the mechanism contributes."
    )


# parameter -> (source, sentence). `{v}` is substituted with "mean [q05, q95]".
NOTES: dict[str, tuple[str, str | Callable[[dict, dict | None], str | None]]] = {
    "tau_cleav": ("tau_cleav", lambda m, sib: _tau_cleav_note(m)),
    "tau_mech": ("tau_mech", lambda m, sib: _tau_mech_note(m)),
    "sigma_agent": ("coefficients", lambda m, sib: _sigma_agent_note(m)),
    "b_combo": (
        "coefficients",
        "combination arms do report higher rates -- on this corpus, where every arm is a "
        "ClinicalTrials.gov record. On the literature-extended corpus the same coefficient "
        "reaches +1.091 without a source indicator, because every combination arm is a "
        "registry arm and none of the 194 literature arms is one, so it estimates the "
        "corpus rather than the regimen. That pair was measured before the corpus rebuild "
        "and before `b_source` existed, so the registry value beside it there is +0.195 "
        "rather than the figure above; both are recorded under "
        "`b_combo_without_source_term` in `artifacts/source_confounding.json` and neither "
        "is regenerated by any target, because the specification that produced them was "
        "replaced in response to them. See negative result 33.",
    ),
    "b_log_n": ("coefficients", _b_log_n_note),
    "b_dar": ("coefficients", lambda m, sib: _b_dar_note(m)),
    "b_thresh": ("coefficients", _b_thresh_note),
}


def _fmt(cell: dict, signed: bool) -> str:
    """Four decimals, so check_report.py has power on these figures.

    `signed` is False for scale parameters: tau and sigma are positive by construction, so
    a leading "+" on them implies a sign that could have gone the other way.
    """
    if not signed:
        return f"{cell['mean']:.4f} [{cell['q05']:.4f}, {cell['q95']:.4f}]"
    return f"{cell['mean']:+.4f} [{cell['q05']:+.4f}, {cell['q95']:+.4f}]"


def build_block(metrics: dict, sibling: dict | None = None) -> str:
    lines = [BEGIN]
    for name, (where, note) in NOTES.items():
        cell = metrics.get(name) if where.startswith("tau") else (
            metrics.get("coefficients", {}).get(name)
        )
        # Needs an interval, not just a mean: a scale quoted without one overstates what
        # the fit established. An artefact predating the quantiles is skipped rather than
        # printed bare.
        if not cell or "mean" not in cell or "q05" not in cell:
            continue
        signed = name.startswith("b_")
        text = note(metrics, sibling) if callable(note) else note
        if text is None:
            continue
        lines.append(f"`{name}` {_fmt(cell, signed)} -- {text}")
        lines.append("")
    sa = metrics.get("seed_agreement")
    if sa:
        worst = max(sa["by_parameter"], key=lambda k: sa["by_parameter"][k])
        lines.append(
            f"Convergence stands in for R-hat: the model is refit under a second seed and "
            f"posterior means compared. The worst standardized gap is "
            f"{sa['worst_standardized_gap']:.4f} pooled standard deviations, on "
            f"`{worst}`, against a threshold of {sa['threshold']} -- "
            + ("acceptable." if sa["converged"] else "NOT converged.")
        )
    if lines[-1] == "":
        lines.pop()
    lines.append(END)
    return "\n".join(lines)


def _bootstrap_ci(values, n_boot: int = 2000, seed: int = 0):
    """Same estimator fit_forward.py uses, so a derived interval matches a stored one."""
    import numpy as np

    arr = np.asarray([v for v in values if np.isfinite(v)])
    if len(arr) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_boot)]
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def _marker_indent(text: str, marker: str) -> str:
    """The whitespace in front of a block's opening marker, which is its context.

    A generated block sits inside a numbered list item in one document and at the top level
    of a section in another. Markdown reads four leading spaces at the top level as a code
    fence, so a fixed indent renders the table in `MODEL_CARD.md` as literal text while a
    bare block ends the list in `findings.md`. The marker already records which it is.
    """
    m = re.search(r"^([ \t]*)" + re.escape(marker), text, re.M)
    return m.group(1) if m else ""


def build_rank_resolution_block(doc: dict) -> str | None:
    """The table behind "it does not rank", from artifacts/rank_resolution.json.

    Hand-typed until now, and two of its six rows were stale: the median leader probability
    had moved from 0.522 to 0.500, and the count of queries where every displayed candidate
    sits in one tie group had fallen from 192 to 48 when the display order inside a group
    became the patient's weighting. The row that matters did not move -- 0 of 192 queries
    produce a decisive leader -- which is exactly why the stale neighbours went unnoticed.
    """
    s_ = doc.get("summary") or {}
    need = ("queries", "decisive_leader", "all_shown_in_one_group",
            "head_group_size_median", "head_share_of_passing_median", "lead_p_median",
            "distinct_targets", "distinct_profiles")
    if not all(k in s_ for k in need):
        return None
    n = s_["queries"]
    lines = [
        RR_BEGIN, "",
        "| quantity | value |",
        "|---|---|",
        f"| queries swept ({s_['distinct_targets']} targets x "
        f"{s_['distinct_profiles']} comorbidity profiles) | {n} |",
        f"| **queries with a decisive leader** | **{s_['decisive_leader']}** |",
        "| queries where every displayed candidate is in one tie group | "
        f"{s_['all_shown_in_one_group']} |",
        f"| median tie-group size at the head | {s_['head_group_size_median']} |",
        "| median share of constraint-passing candidates in that group | "
        f"{s_['head_share_of_passing_median'] * 100:.0f}% |",
        f"| median P(leader beats runner-up) | {s_['lead_p_median']:.4f} |",
        "",
        f"**{s_['lead_p_median']:.4f}** against the 0.800 required, and it barely moves "
        "across targets or profiles. This is not a threshold set too strictly: a leader "
        f"that wins {s_['lead_p_median'] * 100:.0f}% of paired draws is a coin flip.",
        "",
        RR_END,
    ]
    return "\n".join(lines)


def build_payload_compression_block(doc: dict, indent: str = "    ") -> str | None:
    """What a mechanism-level model can say about payloads inside one mechanism.

    Every figure is read from `artifacts/payload_axis_compression.json`. The block states
    the rank agreement first, because it is the sharper claim: a flat prediction that still
    ordered the payloads correctly would be useful, and one that does not order them is not.
    """
    summary = doc.get("summary") or {}
    rows = doc.get("rows") or []
    gran = doc.get("granularity") or []
    rho = summary.get("mean_within_mechanism_spearman")
    if rho is None or not rows:
        return None
    ranked = [r for r in rows if "within_mechanism_spearman" in r]
    if not ranked:
        return None
    lo = min(ranked, key=lambda r: r["within_mechanism_spearman"])
    hi = max(ranked, key=lambda r: r["within_mechanism_spearman"])
    ocular = next(
        (r for r in rows if r["axis"] == "ocular" and r["mechanism"] == "tubulin"), None
    )

    lines = [PAC_BEGIN, ""]
    lines.append(
        f"Within `{lo['mechanism']}`, over the payloads with enough observed cells, the "
        f"model's ordering of the payloads on an organ axis is uncorrelated with the "
        f"observed ordering: **mean Spearman {rho:+.4f}** across "
        f"{len(ranked)} axes, from {lo['within_mechanism_spearman']:+.4f} on "
        f"{lo['axis']} to {hi['within_mechanism_spearman']:+.4f} on {hi['axis']}."
    )
    if ocular:
        pay = ocular["payloads"]
        cells = ocular.get("payload_cells") or {}
        mdl = ocular.get("model_by_payload") or {}
        lines.append("")
        lines.append(
            f"On the ocular axis the observed rates span **{ocular['observed_lo']:.4f} to "
            f"{ocular['observed_hi']:.4f}, a factor of {ocular['observed_fold']:.2f}**, and "
            f"the model spans **{ocular['model_fold']:.2f}**."
        )
        lines.append("")
        lines.append("| payload | observed | cells | model |")
        lines.append("|---|---|---|---|")
        for k in sorted(pay, key=lambda k: -pay[k]):
            lines.append(
                f"| {k} | {pay[k]:.4f} | {cells.get(k, '?')} | "
                f"{mdl.get(k, float('nan')):.4f} |"
            )
    g_oc = next((r for r in gran if r["axis"] == "ocular"), None)
    if g_oc:
        others = [
            r for r in gran
            if r["axis"] in ("cardiovascular", "hepatic") and r.get("family_fold")
        ]
        lines.append("")
        text = (
            f"Which granularity recovers the spread, axis by axis: on ocular "
            f"**{g_oc['payload_fold']:.2f}x at payload, {g_oc['family_fold']:.2f}x at "
            f"family, {g_oc['cleavable_fold']:.2f}x at cleavability**"
        )
        for r in others:
            text += (
                f"; on {r['axis']} **{r['payload_fold']:.2f}x and "
                f"{r['family_fold']:.2f}x**"
            )
        text += (
            ". So payload family is a serviceable proxy for most organ axes and a useless "
            "one for ocular -- and the fit has the family level disabled, which leaves "
            "cleavability as the whole vocabulary."
        )
        lines.append(text)
    lines.append("")
    lines.append(PAC_END)
    return ("\n" + indent).join(lines).replace("\n" + indent + "\n", "\n\n")


def build_source_axis_block(doc: dict, metrics: dict, indent: str = "    ") -> str | None:
    """Section 34's figures, which were hand-typed and went stale when the corpus grew.

    Every number here moved when the expanded corpus gained five agents with arms from both
    sources -- the comparison's denominator went from 12 agents to 17, the widest negative
    axis changed from cardiovascular to pulmonary, and the between-axis scale fell from
    0.716 to 0.628. The guard caught exactly one of those, because the others were stated to
    two decimals and a two-decimal figure passes against 22,000 artefact values by accident.
    See negative result 38.

    The direction claim is derived too: which axes papers over-report relative to the
    registry is a statement about signs, and signs are in the artefact.
    """
    summary = doc.get("summary") or {}
    axes = doc.get("axes") or []
    if not summary or not axes:
        return None
    ranked = sorted(axes, key=lambda r: -r["gap_logit"])
    hi, lo = ranked[0], ranked[-1]
    over = [r for r in ranked if r["gap_logit"] > 0]
    under = [r for r in ranked if r["gap_logit"] <= 0]
    tau_mech = (metrics.get("tau_mech") or {}).get("mean")

    lines = [SAX_BEGIN, ""]
    lines.append(
        f"Measured on the **{summary['agents_with_both_sources']} agents with arms from "
        "*both* sources**, which holds the chemistry fixed so the difference is reporting "
        "rather than drug, the literature-minus-registry gap runs from "
        f"**{lo['gap_logit']:+.4f} logit on {lo['axis']}** to "
        f"**{hi['gap_logit']:+.4f} on {hi['axis']}**: heterogeneity "
        f"**Q = {summary['heterogeneity_q']:.1f} on {summary['df']} degrees of freedom, "
        f"p = {summary['p']:.3g}**, between-axis standard deviation "
        f"**{summary['between_axis_sd']:.4f}**"
        + (
            f" -- larger than `tau_mech` at {tau_mech:.4f}, the mechanism-by-axis scale the "
            "model exists to estimate."
            if tau_mech and summary["between_axis_sd"] > tau_mech
            else f" -- against `tau_mech` at {tau_mech:.4f}, the mechanism-by-axis scale the "
                 "model exists to estimate, which it no longer exceeds."
            if tau_mech
            else "."
        )
    )
    lines.append("")
    lines.append(
        "The direction is what makes it a specification error rather than noise. Papers "
        "report **more** than the registry on "
        + ", ".join(f"{r['axis']} ({r['gap_logit']:+.4f})" for r in over)
        + " -- the signature findings those papers are about -- and **less** on "
        + ", ".join(f"{r['axis']} ({r['gap_logit']:+.4f})" for r in under[-3:][::-1])
        + ", which are background and fall below a \"most common adverse events\" cut."
    )
    n_cmp = summary.get("axes_compared")
    excluded = summary.get("axes_excluded") or []
    if n_cmp is not None:
        lines.append("")
        text = (
            f"{n_cmp} of the {n_cmp + len(excluded)} axes are compared. An axis needs at "
            f"least {summary.get('min_per_side', 6)} observations on each side to enter."
        )
        if excluded:
            # Every exclusion so far has been short on the literature side, which makes the
            # exclusions the same finding as the gaps. If one is ever short on the registry
            # side instead, that sentence stops being true and the block must not say it.
            lit_short = [r for r in excluded if r.get("short_side") == "literature"]
            text += (
                " The ones that do not qualify are the same finding in miniature: "
                + ", ".join(
                    f"{r['axis']} has {r['n_literature']} literature observations against "
                    f"{r['n_registry']} registry"
                    for r in sorted(excluded, key=lambda r: r["n_literature"])
                )
                + (
                    " -- short on the literature side in every case, which is the reporting "
                    "selection the included axes quantify, not a gap in the measurement."
                    if len(lit_short) == len(excluded)
                    else " -- and not all of them short on the literature side, so these "
                         "are not all the same effect as the gaps above."
                )
            )
        lines.append(text)
    lines.append("")
    lines.append(SAX_END)
    # This block sits inside a numbered list item, so every line after the first carries the
    # item's indent or markdown ends the list and renumbers what follows. The first line is
    # left bare because the marker it replaces already has the indent in front of it.
    return ("\n" + indent).join(lines).replace("\n" + indent + "\n", "\n\n")


def build_results_block(metrics: dict, dose: dict | None) -> str | None:
    """The headline evaluation table.

    Generated because it is the most consequential table in the project and was typed by
    hand at three decimals, where the number guard has little power -- its Spearman
    interval traced to nothing and passed only by coincidence.
    """
    import numpy as np

    cv = metrics.get("cv", {})
    rows: list[tuple[str, str, str, str, str, str]] = []
    labels = [
        ("leave_one_agent_out", "leave-one-agent-out"),
        ("leave_one_mechanism_out", "leave-one-mechanism-out"),
        ("leave_one_family_out", "leave-one-family-out"),
    ]
    for key, label in labels:
        v = cv.get(key)
        if not v:
            continue
        n = len(v.get("folds", []))
        best = max(v["macro_auc_mech_baseline"], v["macro_auc_global_baseline"])
        lo, hi = v["delta_auc_ci"]
        excl = "excludes 0" if (lo > 0) == (hi > 0) else "includes 0"
        bold = "**" if excl == "excludes 0" else ""
        rows.append((
            f"within-arm ranking, {label} ({n})",
            f"{v['macro_auc']:.4f}", f"{best:.4f}",
            f"{bold}{v['delta_auc_mean']:+.4f}{bold}",
            f"[{lo:+.4f}, {hi:+.4f}]", excl,
        ))

    sp = cv.get("leave_one_agent_out", {}).get("across_agent_spearman", {})
    if sp.get("model"):
        mv = [v for v in sp["model"].values() if np.isfinite(v)]
        if "model_ci" in sp:
            lo, hi = sp["model_ci"]
            note = "includes 0" if (lo <= 0 <= hi) else "excludes 0"
        else:
            # Derived from the stored per-axis values with the same estimator the fit
            # uses, so the figure still traces to an artefact. Runs produced before
            # `model_ci` was persisted take this path.
            lo, hi = _bootstrap_ci(mv)
            note = ("includes 0" if (lo <= 0 <= hi) else "excludes 0") + ", CI derived"
        base = sp.get("global_baseline_mean")
        if base is None and sp.get("global_baseline"):
            base = float(np.nanmean(list(sp["global_baseline"].values())))
        rows.append((
            "across-agent per-axis Spearman",
            f"{float(np.nanmean(mv)):+.4f}",
            f"{base:+.4f}" if base is not None else "--",
            "--", f"[{lo:+.4f}, {hi:+.4f}]", note,
        ))

    if dose:
        lo, hi = dose.get("paired_delta_ci", [float("nan")] * 2)
        baseline_key = f"mean_rho_{dose.get('best_baseline')}_baseline"
        baseline = dose.get(baseline_key)
        rows.append((
            f"dose-modification ordering ({dose.get('n_agents', '?')})",
            f"{dose['mean_rho_model']:+.4f}",
            f"{baseline:+.4f}" if baseline is not None else "--",
            f"{dose['paired_delta_vs_best_baseline']:+.4f}",
            f"[{lo:+.4f}, {hi:+.4f}]",
            "includes 0" if (lo <= 0 <= hi) else "excludes 0",
        ))

    if not rows:
        return None
    out = [RES_BEGIN, "", "| evaluation | model | best baseline | delta | 95% CI | |",
           "|---|---|---|---|---|---|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    out += ["", RES_END]
    return "\n".join(out)


def build_fold_difficulty_block(doc: dict) -> str | None:
    """The four worst folds and what actually predicts fold difficulty."""
    rows = doc.get("folds") or []
    if not rows:
        return None
    claim = doc.get("sole_of_family_claim") or {}
    rho = doc.get("spearman_delta_vs") or {}
    out = [FD_BEGIN, "", "| fold | delta vs baseline | same-payload siblings | "
           "family share of mechanism | sole of family |", "|---|---|---|---|---|"]
    for r in rows[:4]:
        out.append(
            f"| {r['agent'].replace('_', ' ')} | **{r['delta_auc']:+.4f}** | "
            f"{r['same_payload_siblings']} | "
            f"{r['family_share_of_mechanism']:.2f} | "
            f"{'yes' if r['sole_of_family'] else 'no'} |"
        )
    out += ["", (
        f"Sole-of-family agents among the four worst folds: "
        f"{claim.get('sole_among_worst_four')}/4. Mean delta "
        f"{claim.get('mean_delta_sole'):+.4f} for the {claim.get('n_sole')} "
        f"sole-of-family agents against {claim.get('mean_delta_shared'):+.4f} for the "
        f"{claim.get('n_shared')} that share one -- no separation. Rank correlation of "
        f"fold delta with same-payload siblings "
        f"{rho.get('same_payload_siblings'):+.3f}, with family share of its mechanism "
        f"{rho.get('family_share_of_mechanism'):+.3f}."
    ), FD_END]
    return "\n".join(out)


def build_enrichment_block(doc: dict) -> str | None:
    """The exclusion-criteria enrichment table, with significance marked.

    Generated because the hand-written version gave a 13.6x ratio resting on seven trials
    the same visual weight as one resting on six hundred, and because its boilerplate
    sentence misreported which organs are flat.
    """
    import sys
    from pathlib import Path as _P

    sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "src"))
    from adctox.comorbidity.exclusion_prior import _bh_critical_p

    rows = doc.get("by_mechanism") or []
    if not rows:
        return None
    crit = _bh_critical_p([c.get("p") for r in rows for c in r["cells"]])
    organs = ["pulmonary", "neurologic", "ocular", "hepatic"]
    base = doc.get("base_rate") or {}   # organ -> control rate

    out = [ENR_BEGIN, "", "| payload mechanism | n | " + " | ".join(organs) + " |",
           "|---|---|" + "---|" * len(organs)]
    if base:
        out.append(
            f"| base rate (oncology) | {doc.get('n_control', 0):,} | "
            + " | ".join(f"{100 * base[o]:.1f}%" if o in base else "--" for o in organs)
            + " |"
        )
    for r in sorted(rows, key=lambda r: -r.get("n_trials", 0)):
        cells = {c["organ"]: c for c in r["cells"]}
        n = r.get("n_trials", 0)
        vals = []
        for o in organs:
            c = cells.get(o)
            if c is None:
                vals.append("--")
                continue
            ratio = c["odds_ratio"]
            sig = c.get("p") is not None and c["p"] <= crit
            txt = f"{ratio:.1f}x"
            if sig and ratio >= 2.0:
                txt = f"**{txt}**"
            elif not sig:
                txt = f"{txt}&dagger;"
            vals.append(txt)
        out.append(f"| {r['mechanism']} | {n:,} | " + " | ".join(vals) + " |")
    # The daggered cells split into two kinds and the footnote has to say which, because
    # a null ratio and an underpowered large ratio are not the same failure.
    big_insig = [
        (r["mechanism"], c["organ"], c["odds_ratio"], r.get("n_trials", 0))
        for r in rows for c in r["cells"]
        if c["odds_ratio"] >= 2.0 and not (c.get("p") is not None and c["p"] <= crit)
    ]
    big_txt = ", ".join(
        f"{m}/{o} at {ratio:.1f}x on {n} trials" for m, o, ratio, n in
        sorted(big_insig, key=lambda x: -x[2])
    )
    out += [
        "",
        "Bold is enriched at least 2x **and** significant under Benjamini-Hochberg across "
        f"all {sum(len(r['cells']) for r in rows)} (mechanism, organ) cells at q=0.05 "
        f"(critical p = {crit:.2e}). A dagger marks a cell not distinguishable from the "
        "base rate. For most of them the ratio is simply near 1 and there is nothing to "
        "distinguish. "
        + (
            f"The ones that matter are the large ratios that still fail: {big_txt}. "
            "Each sits on a mechanism carried by a single drug, so the figure is one "
            "sponsor's protocol habits rather than a property of the chemistry, and the "
            "product suppresses it rather than displaying it."
            if big_insig else
            "No cell above 2x fails the correction."
        ),
        ENR_END,
    ]
    return "\n".join(out)


def build_hard_flag_block(doc: dict) -> str | None:
    """What the label-rule layer still has to carry, and what it no longer does."""
    rows = doc.get("flags") or []
    if not rows:
        return None
    lines = [
        HFN_BEGIN, "",
        "| label rule | serious rate | model alone | with rule | |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        verdict = "**load-bearing**" if r["rule_is_load_bearing"] else "confirmatory"
        lines.append(
            f"| `{r['flag']}` ({r['source_label']}) | {r['serious_rate']:.4f} | "
            f"{r['band_model_alone']} | {r['band_with_rule']} | {verdict} |"
        )
    carried = [r for r in rows if r["rule_is_load_bearing"]]
    free = [r for r in rows if not r["rule_is_load_bearing"]]
    lines += ["", (
        f"The rule layer is load-bearing for **{doc['n_load_bearing']} of "
        f"{doc['n_flags']}** flags. It is confirmatory for "
        + ", ".join(f"`{r['flag']}`" for r in free)
        + " -- both deruxtecan/pulmonary -- which means the model now reaches the "
          "boxed-warning band there on its own. That matters beyond tidiness: while the "
          "rule was raising that band, the ILD case study was deciding its own question."
    )]
    pay = sorted({f"{r['payload']}/{r['axis']}" for r in carried
                  if r["mechanism"] == "tubulin"})
    if pay:
        lines += ["", (
            "What the rules still carry is the informative part: "
            + ", ".join(pay)
            + ". Both are payload-level effects inside a single mechanism, and both are "
            "boxed warnings the model ranks `low`. That is not a bug to fix -- it is the "
            "same identification limit this report measures three other ways. The "
            "mechanism level is too coarse to separate MMAE from MMAF, and the payload "
            "family level does not converge at any corpus size reachable here, so these "
            "two warnings cannot come from the fit and have to come from the label."
        )]
    lines.append(HFN_END)
    return "\n".join(lines)


def build_label_change_block(doc: dict) -> str | None:
    """The Module B anticipatory result.

    Generated because the report described this evaluation's design and power and then
    reported no outcome at all -- the artefact had been quarantined since the centering
    bug and the summary was only ever printed to stdout.
    """
    s = doc.get("summary") or {}
    if not s.get("n_scored"):
        return None
    hits, n = s["top3_hits"], s["n_scored"]
    lines = [
        LCE_BEGIN,
        "",
        f"**{n} of {s['n_scored'] + s['n_not_scorable']} events were scorable**; the rest "
        f"predate a corpus large enough to fit on, and are reported as not scorable "
        f"rather than scored on noise.",
        "",
        f"| quantity | value |",
        f"|---|---|",
        f"| events scored | {n} across {s.get('n_independent_drugs', '?')} independent "
        f"drugs |",
        f"| mean predicted rank | {s['mean_rank']:.4f} of 14 (null {s['null_mean_rank']}) |",
        f"| in top three | {hits} of {n} |",
        f"| one-sided p | {s['p_value']:.4f}"
        f"{' (significant)' if s['significant'] else ' (not significant)'} |",
        "",
    ]
    mh = s.get("min_hits_for_significance")
    if mh is not None:
        lines.append(
            f"The mean rank beats the null, but the test does not reach significance. "
            f"And it barely could: at {n} scorable events only **{mh} of {n}** or better "
            f"reaches p<0.05, so a single miss ends it. That is the same defect as the "
            f"unfireable AUC gate elsewhere in this report -- a test whose outcome was "
            f"nearly determined by its own sample size. It is reported as a case series "
            f"with a permutation test, which is what it is."
        )
    else:
        lines.append(
            f"No outcome at {n} scorable events could have reached p<0.05. The test was "
            f"unfireable as specified, and saying so is the result."
        )
    lines.append(LCE_END)
    return "\n".join(lines)


def build_censoring_block(doc: dict) -> str | None:
    """The b_thresh sensitivity table, from artifacts/censoring_sensitivity.json."""
    if not all(k in doc for k in (k for k, _ in CENS_ROWS)):
        return None
    lines = [CENS_BEGIN, "", "| treatment | `b_thresh` |", "|---|---|"]
    for key, label in CENS_ROWS:
        cell = doc[key].get("b_thresh")
        if not cell:
            return None
        lines.append(
            f"| {label} | {cell['mean']:+.4f} "
            f"[{cell['q05']:+.4f}, {cell['q95']:+.4f}] |"
        )
    sub = doc["threshold_0_only"].get("b_thresh", {})
    pa = doc.get("profile_agreement", {})
    n_arms = pa.get("n_arms_in_complete_subset")
    # The substance check: do the censored and completely-reported corpora agree on which
    # organ each mechanism hits? Generated, because the rerun that stamped this artefact
    # would otherwise have left three hand-typed Spearmans stale.
    rho = pa.get("spearman_by_mechanism") or {}
    LABEL = {"dna_cleave": "calicheamicin", "topo1": "topoisomerase-I",
             "tubulin": "tubulin", "dna_crosslink": "PBD/IGN",
             "dna_alkyl": "duocarmycin", "protein_synth": "immunotoxin"}
    if rho:
        worst = min(rho.values())
        lines += ["", (
            "Agreement on the mechanism organ profiles, censored full corpus against the "
            "completely-reported subset: "
            + ", ".join(f"{LABEL.get(m, m)} {v:+.4f}"
                        for m, v in sorted(rho.items(), key=lambda kv: -kv[1]))
            + f" (sorted, so the binding figure is the last at {worst:+.4f}). The two "
            "corpora agree on which organ each payload mechanism hits, so the censoring "
            "treatment recovers signal that "
            "survives in data which never needed correcting. Had they disagreed, the "
            "project would have been resting on its own correction."
        )]
    lines += [
        "",
        f"The completely-reported subset is only {n_arms} arms, so its own interval for "
        f"this coefficient spans [{sub.get('q05', float('nan')):+.4f}, "
        f"{sub.get('q95', float('nan')):+.4f}] -- which is why agreement between the "
        "corpora is assessed on the mechanism profiles rather than on coefficients.",
        CENS_END,
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", type=Path,
                    default=Path("artifacts/forward_other_metrics.json"))
    ap.add_argument("--censoring", type=Path,
                    default=Path("artifacts/censoring_sensitivity.json"))
    ap.add_argument("--dose-mod", type=Path,
                    default=Path("artifacts/dose_mod_eval.json"))
    ap.add_argument("--label-change", type=Path,
                    default=Path("artifacts/label_change_eval.json"))
    ap.add_argument("--hard-flags", type=Path,
                    default=Path("artifacts/hard_flag_necessity.json"))
    ap.add_argument("--fold-difficulty", type=Path,
                    default=Path("artifacts/fold_difficulty.json"))
    ap.add_argument("--enrichment", type=Path,
                    default=Path("artifacts/exclusion_enrichment_exclusion.json"))
    # Both documents quoted the same parameters and both were stale. The model card was
    # worse off: check_report.py only scanned report/, so its figures were never checked
    # at all.
    ap.add_argument("--report", type=Path, nargs="+",
                    default=[Path("report/findings.md"), Path("docs/MODEL_CARD.md")])
    ap.add_argument("--rank-resolution", type=Path,
                    default=Path("artifacts/rank_resolution.json"))
    ap.add_argument("--payload-compression", type=Path,
                    default=Path("artifacts/payload_axis_compression.json"))
    ap.add_argument("--source-axis", type=Path,
                    default=Path("artifacts/source_axis_heterogeneity.json"))
    ap.add_argument("--check", action="store_true",
                    help="fail if the block is out of date instead of rewriting it")
    args = ap.parse_args()

    if not args.metrics.exists():
        print(f"{args.metrics} absent; run `make forward` first")
        return 1
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    # The other event table, for the notes that compare the two. Named from the given path
    # rather than hardcoded, so pointing --metrics at a different artefacts directory picks
    # up that directory's sibling and not this one's.
    other_kind = "serious" if "_other_" in args.metrics.name else "other"
    sibling_path = args.metrics.with_name(f"forward_{other_kind}_metrics.json")
    sibling = (
        json.loads(sibling_path.read_text(encoding="utf-8"))
        if sibling_path.exists() else None
    )
    block = build_block(metrics, sibling)

    dose = (
        json.loads(args.dose_mod.read_text(encoding="utf-8"))
        if args.dose_mod.exists() else None
    )
    res_block = build_results_block(metrics, dose)
    fd_block = (
        build_fold_difficulty_block(
            json.loads(args.fold_difficulty.read_text(encoding="utf-8"))
        )
        if args.fold_difficulty.exists() else None
    )
    enr_block = (
        build_enrichment_block(
            json.loads(args.enrichment.read_text(encoding="utf-8"))
        )
        if args.enrichment.exists() else None
    )
    hfn_block = (
        build_hard_flag_block(json.loads(args.hard_flags.read_text(encoding="utf-8")))
        if args.hard_flags.exists() else None
    )
    lce_block = (
        build_label_change_block(
            json.loads(args.label_change.read_text(encoding="utf-8"))
        )
        if args.label_change.exists() else None
    )
    # These two are built per document rather than once, because their indent comes from
    # where the marker sits in that document.
    rr_block = (
        build_rank_resolution_block(
            json.loads(args.rank_resolution.read_text(encoding="utf-8"))
        )
        if args.rank_resolution.exists() else None
    )
    pac_doc = (
        json.loads(args.payload_compression.read_text(encoding="utf-8"))
        if args.payload_compression.exists() else None
    )
    sax_doc = (
        json.loads(args.source_axis.read_text(encoding="utf-8"))
        if args.source_axis.exists() else None
    )
    cens_block = None
    if args.censoring.exists():
        cens_block = build_censoring_block(
            json.loads(args.censoring.read_text(encoding="utf-8"))
        )

    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    cens_pattern = re.compile(
        re.escape(CENS_BEGIN) + r".*?" + re.escape(CENS_END), re.S
    )
    res_pattern = re.compile(re.escape(RES_BEGIN) + r".*?" + re.escape(RES_END), re.S)
    lce_pattern = re.compile(re.escape(LCE_BEGIN) + r".*?" + re.escape(LCE_END), re.S)
    hfn_pattern = re.compile(re.escape(HFN_BEGIN) + r".*?" + re.escape(HFN_END), re.S)
    enr_pattern = re.compile(re.escape(ENR_BEGIN) + r".*?" + re.escape(ENR_END), re.S)
    fd_pattern = re.compile(re.escape(FD_BEGIN) + r".*?" + re.escape(FD_END), re.S)
    sax_pattern = re.compile(re.escape(SAX_BEGIN) + r".*?" + re.escape(SAX_END), re.S)
    pac_pattern = re.compile(re.escape(PAC_BEGIN) + r".*?" + re.escape(PAC_END), re.S)
    rr_pattern = re.compile(re.escape(RR_BEGIN) + r".*?" + re.escape(RR_END), re.S)
    rc = 0
    for doc in args.report:
        text = doc.read_text(encoding="utf-8")
        if res_block and res_pattern.search(text):
            replaced = res_pattern.sub(lambda _: res_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: results table is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: results table regenerated")
        if rr_block and rr_pattern.search(text):
            replaced = rr_pattern.sub(lambda _: rr_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: rank-resolution block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: rank-resolution block regenerated")
        pac_block = (
            build_payload_compression_block(
                pac_doc, indent=_marker_indent(text, PAC_BEGIN)
            )
            if pac_doc else None
        )
        sax_block = (
            build_source_axis_block(
                sax_doc, metrics, indent=_marker_indent(text, SAX_BEGIN)
            )
            if sax_doc else None
        )
        if pac_block and pac_pattern.search(text):
            replaced = pac_pattern.sub(lambda _: pac_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: payload-compression block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: payload-compression block regenerated")
        if sax_block and sax_pattern.search(text):
            replaced = sax_pattern.sub(lambda _: sax_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: source-axis block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: source-axis block regenerated")
        if fd_block and fd_pattern.search(text):
            replaced = fd_pattern.sub(lambda _: fd_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: fold-difficulty block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: fold-difficulty block regenerated")
        if enr_block and enr_pattern.search(text):
            replaced = enr_pattern.sub(lambda _: enr_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: enrichment block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: enrichment block regenerated")
        if hfn_block and hfn_pattern.search(text):
            replaced = hfn_pattern.sub(lambda _: hfn_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: hard-flag block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: hard-flag block regenerated")
        if lce_block and lce_pattern.search(text):
            replaced = lce_pattern.sub(lambda _: lce_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: label-change block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: label-change block regenerated")
        if cens_block and cens_pattern.search(text):
            replaced = cens_pattern.sub(lambda _: cens_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: censoring-sensitivity block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: censoring-sensitivity block regenerated")
        if not pattern.search(text):
            print(
                f"{doc} has no generated block. Insert these two markers around the "
                f"fitted-parameter list:\n  {BEGIN}\n  {END}"
            )
            rc = 1
            continue
        updated = pattern.sub(lambda _: block, text)
        if updated == text:
            print(f"{doc}: fitted-parameter block already current")
            continue
        if args.check:
            print(
                f"{doc}: fitted-parameter block is STALE against {args.metrics}. "
                "Run `python scripts/sync_report_numbers.py` to regenerate it."
            )
            rc = 1
            continue
        doc.write_text(updated, encoding="utf-8")
        print(f"{doc}: fitted-parameter block regenerated from {args.metrics}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
