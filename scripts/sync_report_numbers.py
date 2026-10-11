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

ABL_BEGIN = "<!-- generated: corpus-ablation -->"
ABL_END = "<!-- /generated: corpus-ablation -->"

RR_BEGIN = "<!-- generated: rank-resolution -->"
RR_END = "<!-- /generated: rank-resolution -->"

PAC_BEGIN = "<!-- generated: payload-compression -->"
PAC_END = "<!-- /generated: payload-compression -->"

SAX_BEGIN = "<!-- generated: source-axis -->"
SAX_END = "<!-- /generated: source-axis -->"

INV_BEGIN = "<!-- generated: inverse-retrieval -->"
INV_END = "<!-- /generated: inverse-retrieval -->"

R1_BEGIN = "<!-- generated: rank1 -->"
R1_END = "<!-- /generated: rank1 -->"

THA_BEGIN = "<!-- generated: threshold-accuracy -->"
THA_END = "<!-- /generated: threshold-accuracy -->"

PCH_BEGIN = "<!-- generated: posterior-choice -->"
PCH_END = "<!-- /generated: posterior-choice -->"

AAX_BEGIN = "<!-- generated: across-agent-per-axis -->"
AAX_END = "<!-- /generated: across-agent-per-axis -->"

OLG_BEGIN = "<!-- generated: objective-label-gap -->"
OLG_END = "<!-- /generated: objective-label-gap -->"

AAT_BEGIN = "<!-- generated: across-agent-trend -->"
AAT_END = "<!-- /generated: across-agent-trend -->"

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


def _cleavability_balance() -> dict | None:
    """What the cleavability contrast rests on, from artifacts/design_balance.json."""
    path = Path("artifacts/design_balance.json")
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    # Keyed to the corpus the fitted-parameter block describes, which is the registry one.
    return (doc.get("corpora") or {}).get("registry", {}).get("cleavability")


def _tau_cleav_note(metrics: dict) -> str | None:
    """The scale of the cleavability contrast, and what it is estimated from.

    This note used to call cleavability "the one design axis the corpus identifies
    comfortably", on the grounds that a binary needs only 8 agents against the 40 a
    mechanism level needs. The claim was checked against the wrong count. Eight is a floor
    on the *minority* level, and the registry corpus has **three** non-cleavable agents, all
    of them tubulin -- so for every other payload mechanism the contrast has no variation at
    all and the scale is an effect estimated inside one mechanism under a corpus-wide name.
    See negative result 54.
    """
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
             "mechanism does, which is a reversal of what this report says elsewhere and "
             "needs checking before it is quoted"
    )
    text = (
        "the scale of the cleavable-versus-non-cleavable linker contrast across axes. "
        f"{clear}, and {rel} -- {direction}."
    )
    bal = _cleavability_balance()
    if not bal:
        return text + (" What it is estimated from is not measured in this tree; run "
                       "`make design-balance`.")
    floor = bal["minority_agents"]
    varying = bal["mechanisms_with_variation"]
    if bal["meets_binary_agent_floor"] and not bal["nested_in_one_mechanism"]:
        return text + (
            f" It rests on {floor} agents at the minority level, above the 8 a binary "
            f"contrast needs, with variation inside {len(varying)} of "
            f"{bal['n_mechanisms']} mechanisms -- so it is a contrast between chemistries "
            "and not within one of them."
        )
    return text + (
        f" **It rests on {floor} agents at the minority level, below the {8} a binary "
        f"contrast needs**, and all of them sit in "
        + (f"one mechanism ({varying[0]})" if len(varying) == 1 else
           f"{len(varying)} of {bal['n_mechanisms']} mechanisms")
        + ". So this is not the comfortably identified design axis this report used to call "
        "it: the contrast has no variation at all in the other mechanisms, and removing "
        f"{varying[0] if varying else 'that mechanism'} would remove it entirely. On the "
        "corpus merged with the hand-transcribed database the minority level reaches 17 "
        "agents across three mechanisms, which is the first corpus where the contrast is "
        "between chemistries rather than inside one."
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


# Stage key -> the label the report uses. Hand-written because the keys are identifiers and
# the labels are prose, and a generated label would read like one.
ABLATION_LABELS = {
    "ctgov_original_agent_list": "ClinicalTrials.gov, the original 18-agent list",
    "ctgov_literature_agent_list": "ClinicalTrials.gov, the literature's agent list",
    "plus_literature_arms": "+ literature arms for agents already present",
    "plus_literature_agents": "+ literature agents",
    "plus_transcribed": "+ the hand-transcribed database",
}


def build_ablation_block(doc: dict) -> str | None:
    """The corpus stages, from artifacts/corpus_ablation.json.

    Hand-typed until the fifth stage arrived, and a hand-typed table does not grow a row.
    The stage that matters most is the last: it is the first that is not a reading of
    ClinicalTrials.gov plus the open-access literature, and the first to cross the plan's
    identification floor and to make a fourth mechanism fold viable.
    """
    stages = doc.get("stages") or {}
    order = [k for k in ABLATION_LABELS if k in stages]
    if len(order) < 2:
        return None
    lines = [
        ABL_BEGIN, "",
        "| stage | agents | arms in the grid | cells | cells that identify a design "
        "coefficient | ratio against 100 design parameters | observed | "
        "viable LOMO folds |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key in order:
        st = stages[key]
        folds = sum(1 for m in (st.get("mechanisms") or {}).values()
                    if m.get("viable_fold"))
        last = key == order[-1]
        bold = (lambda v: f"**{v}**") if last else (lambda v: str(v))
        ratio = st["cells_per_design_parameter"]
        lines.append(
            f"| {ABLATION_LABELS[key]} | {bold(st['n_agents'])} | {st['n_arms']} | "
            f"{st['n_cells']:,} | {bold(st['identifying_cells'])} | "
            f"{bold(str(ratio) + ' : 1')} | "
            f"{st['observed_share'] * 100:.1f}% | {bold(folds)} |"
        )
    # The nesting verdict belongs with the table: a stage that is not a superset of the one
    # before it makes every difference in the table ambiguous between arms added and arms
    # dropped.
    nesting = doc.get("nesting") or []
    if nesting:
        dropped = sum(n.get("corpus_arms_dropped", 0) for n in nesting)
        lines += ["", (
            f"Each stage is a superset of the one before it -- {len(nesting)} transitions, "
            f"**{dropped} corpus arms dropped** across all of them -- so a difference in "
            "this table is always arms added and never arms lost."
        )]
    lines += ["", ABL_END]
    return "\n".join(lines)


def build_inverse_retrieval_block(doc: dict, indent: str = "") -> str | None:
    """Does the system recover approved ADC designs? From artifacts/inverse_retrieval.json.

    The plan made this Module A's headline validation and gave it the week's most important
    day. The block is built slot by slot and in both variants, because the difference
    between them is the finding: the precedent objective can recover a design by having
    seen it, and computing that objective on *other* targets is what separates design
    inference from memorisation.
    """
    results = doc.get("results")
    summary = doc.get("summary") or {}
    if not results or "with_precedent" not in summary:
        return None
    slots = list(doc.get("slots") or [])
    lines = [
        INV_BEGIN, "",
        "| slot | informative in | matched top-1 | chance | excess | "
        "excess, precedent on other targets |",
        "|---|---|---|---|---|---|",
    ]
    for slot in slots:
        n = exp = hit = 0
        hit_adj = 0
        for agent in results:
            wp = agent["with_precedent"]
            if slot not in wp["informative_slots"]:
                continue
            n += 1
            exp += wp["chance"][slot]
            hit += int(bool(wp["per_slot_top1"].get(slot)))
            pa = agent.get("precedent_adjusted") or {}
            hit_adj += int(bool((pa.get("per_slot_top1") or {}).get(slot)))
        if not n:
            continue
        bold = "**" if slot == "dar" else ""
        lines.append(
            f"| {bold}{slot}{bold} | {n} agents | {bold}{hit}{bold} | {exp:.2f} | "
            f"{hit - exp:+.2f} | {hit_adj - exp:+.2f} |"
        )
    wp, pa = summary["with_precedent"], summary.get("precedent_adjusted") or {}
    exact = sum(1 for a in results if a["with_precedent"].get("exact_in_top_k"))
    lines += [
        "",
        "| variant | informative slots | matched | chance | excess | permutation p |",
        "|---|---|---|---|---|---|",
        f"| as the product scores it | {wp['informative_slots_total']} | "
        f"**{wp['matched']}** | {wp['chance_expected']:.2f} | {wp['excess']:+.2f} | "
        f"{wp['permutation_p']:.3f} |",
    ]
    if pa:
        lines.append(
            f"| precedent computed on other targets | {pa['informative_slots_total']} | "
            f"**{pa['matched']}** | {pa['chance_expected']:.2f} | {pa['excess']:+.2f} | "
            f"{pa['permutation_p']:.3f} |"
        )
    lines += [
        "",
        f"{doc.get('n_agents')} approved ADCs over {doc.get('distinct_targets')} distinct "
        f"targets, each scored against a posterior **refitted with that agent held out** -- "
        f"{sum(a['fit_seconds'] for a in results) / 3600:.1f} hours of refitting, without "
        "which the model has already seen the answer. The exact design appears in the "
        f"displayed set for **{exact} of {doc.get('n_agents')}**. Slots whose chance rate "
        f"exceeds {doc.get('uninformative_chance_threshold')} are excluded as "
        "uninformative, which is why isotype and masking carry almost no rows.",
        "",
        INV_END,
    ]
    return ("\n" + indent).join(lines).replace("\n" + indent + "\n", "\n\n")


def build_rank1_block(doc: dict, indent: str = "") -> str | None:
    """The rank-1 factorisation, scored on the ordering rather than the variance."""
    rows = doc.get("per_mechanism")
    if not rows:
        return None
    par = doc.get("parameters") or {}
    lines = [
        R1_BEGIN, "",
        "| mechanism | rank-1 scale | rho(full, rank 1) | worst organ, full | "
        "worst organ, rank 1 |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        moved = "" if r["worst_axis_preserved"] else " **moved**"
        lines.append(
            f"| {r['mechanism']} | {r['scale']:+.3f} | {r['ordering_spearman']:+.3f} | "
            f"{r['worst_axis_full']} | {r['worst_axis_rank1']}{moved} |"
        )
    lines += [
        "",
        f"Rank 1 reproduces **{doc['rank1_share_of_mean_matrix'] * 100:.1f}%** of the "
        f"posterior-mean interaction and "
        f"{doc['rank1_share_per_draw']['median'] * 100:.1f}% of a typical draw, and would "
        f"take the identified design parameters from {par.get('full_interaction_identified')} "
        f"to {par.get('rank1_identified')}"
        + (f", and the identification ratio from {par['identification_ratio_now']}:1 to "
           f"**{par['identification_ratio_under_rank1']}:1**"
           if par.get("identification_ratio_under_rank1") else "")
        + f". The worst organ survives for "
        f"{doc['worst_axis_preserved']} of {len(rows)} mechanisms, and "
        f"{len(doc['negative_scales'])} need a **negative** scale -- not a scaled copy of "
        f"the shared profile but its mirror image. Verdict: *{doc['verdict']}*.",
        "",
        R1_END,
    ]
    return ("\n" + indent).join(lines).replace("\n" + indent + "\n", "\n\n")


def build_threshold_accuracy_block(doc: dict, indent: str = "") -> str | None:
    """How far min(reported %) sits above a cut the caption actually stated."""
    g = doc.get("gap")
    if not g or not doc.get("n_scorable"):
        return None
    lines = [
        THA_BEGIN, "",
        "| quantity | value |",
        "|---|---|",
        f"| AE tables parsed | {doc['ae_tables']} |",
        f"| tables carrying a threshold | {doc['tables_with_a_threshold']} |",
        f"| **tables where both numbers exist** | **{doc['n_scorable']}** |",
        f"| median stated cut | {doc['stated_cut']['median']:g}% |",
        f"| median derived bound | {doc['derived_bound']['median']:g}% |",
        f"| **median overshoot** | **{g['median']:+.2f} pp** |",
        f"| mean overshoot | {g['mean']:+.2f} pp |",
        f"| 90th percentile | {g['p90']:+.2f} pp |",
        f"| worst | **{g['max']:+.2f} pp** |",
        f"| within 1 pp | {g['share_within_1pp'] * 100:.0f}% |",
        f"| within 2 pp | {g['share_within_2pp'] * 100:.0f}% |",
        f"| **over 5 pp** | **{g['share_over_5pp'] * 100:.0f}%** |",
        "",
        "The substitution is tight in the middle and has a tail. It is also the "
        "conservative direction -- a bound set too high widens an interval rather than "
        "narrowing it -- so the cost is power, not correctness. Whether the tail is "
        f"predictable: the overshoot against the printed row count gives rho "
        f"{(doc.get('gap_vs_rows') or {}).get('spearman', float('nan')):+.3f} and against "
        f"the stated cut itself "
        f"{(doc.get('gap_vs_stated_cut') or {}).get('spearman', float('nan')):+.3f}, over "
        f"{doc['n_scorable']} tables. Neither is strong enough to correct the bound, so "
        "the tail is a limitation rather than a bug.",
        "",
        THA_END,
    ]
    return ("\n" + indent).join(lines).replace("\n" + indent + "\n", "\n\n")


def build_posterior_choice_block(doc: dict, indent: str = "") -> str | None:
    """How much the serving choice changes, from artifacts/posterior_choice.json.

    The model card argues the registry posterior should be served and gives a reason --
    `sigma_agent` is collinear with the reporting source on the larger corpora -- without
    saying how much the choice is worth. If switching changed nothing the argument would be
    academic. It does not change nothing.
    """
    s_ = doc.get("summary") or {}
    need = ("agents_a", "agents_b", "queries", "queries_with_identical_designs",
            "mean_designs_in_common", "band_cells_changed", "band_cells_compared",
            "band_change_share")
    if not all(k in s_ for k in need):
        return None
    lines = [
        PCH_BEGIN, "",
        "| quantity | value |",
        "|---|---|",
        f"| posterior A / posterior B, in agents | {s_['agents_a']} / {s_['agents_b']} |",
        f"| queries compared | {s_['queries']} |",
        "| **queries where the two show the same designs** | "
        f"**{s_['queries_with_identical_designs']}** |",
        f"| mean designs in common, of six shown | {s_['mean_designs_in_common']} |",
        f"| organ band cells changed | {s_['band_cells_changed']} of "
        f"{s_['band_cells_compared']} |",
        f"| share of band cells changed | **{s_['band_change_share'] * 100:.0f}%** |",
        "| queries either posterior can rank | "
        f"{s_.get('queries_decisive_a', '--')} / {s_.get('queries_decisive_b', '--')} |",
        "",
        "So the serving choice is not academic: the two posteriors agree on the displayed "
        f"design set in {s_['queries_with_identical_designs']} of {s_['queries']} queries "
        f"and disagree about {s_['band_change_share'] * 100:.0f}% of the organ bands. "
        "Neither can rank, which is the one thing they agree on.",
        "",
        PCH_END,
    ]
    return ("\n" + indent).join(lines).replace("\n" + indent + "\n", "\n\n")


def build_across_agent_per_axis_block(
    doc: dict, composition: dict | None = None, indent: str = ""
) -> str | None:
    """The per-axis across-agent correlations, which went stale without failing the guard.

    Section 3 carried six of these figures as prose -- neurologic +0.61, musculoskeletal
    +0.51, gastrointestinal +0.49, renal -0.57, otologic -0.37, pulmonary -0.27 -- from the
    16-agent corpus, together with the mean and interval. The corpus rebuild moved every
    one, and `check_report.py` reported a clean run on all of them, because each traces to
    `artifacts/superseded/`: the artefact recording what it used to be. The paragraph's
    argument survived the change and its numbers did not, which is the worst version of
    this failure -- a reader checking the reasoning finds it sound.

    So the figures are generated and the argument refers to them by position rather than by
    value. The row counts come from `axis_composition.json` where it is present, because the
    sparsity claim is about evidence and not about the correlation.
    """
    unadj = (doc.get("variants") or {}).get("unadjusted") or {}
    per_axis = unadj.get("per_axis")
    if not per_axis:
        return None
    rows_of = {
        r["axis"]: r.get("registry_rows")
        for r in ((composition or {}).get("axes") or [])
    }
    ordered = sorted(per_axis.items(), key=lambda kv: -kv[1])
    lines = [
        AAX_BEGIN, "",
        "| organ axis | across-agent rho | registry rows |",
        "|---|---|---|",
    ]
    for axis, rho in ordered:
        n = rows_of.get(axis)
        lines.append(f"| {axis} | {rho:+.4f} | {n if n is not None else '--'} |")
    mean, ci = unadj.get("mean_spearman"), unadj.get("ci") or [None, None]
    if mean is not None and ci[0] is not None:
        lines += [
            "",
            f"Mean {mean:+.4f}, bootstrap over axes [{ci[0]:+.4f}, {ci[1]:+.4f}] -- an "
            f"interval spanning zero, against a threshold of +0.3 declared before the run. "
            f"The extremes cancel: the most positive axis is {ordered[0][0]} at "
            f"{ordered[0][1]:+.4f} and the most negative is {ordered[-1][0]} at "
            f"{ordered[-1][1]:+.4f}.",
        ]
    lines += ["", AAX_END]
    return ("\n" + indent).join(lines).replace("\n" + indent + "\n", "\n\n")


def build_objective_label_gap_block(doc: dict, indent: str = "") -> str | None:
    """The bound on `worst_axis_risk` against the rate on `worst_axis`.

    Generated because the medians are exact zeros, and a zero typed as `0.000000` does not
    match an artefact's `0.0` -- which is how the number guard found this table typed by
    hand in the first place.
    """
    need = ("unweighted", "weighted", "candidates", "queries", "display_resolution")
    if not all(k in doc for k in need):
        return None
    lines = [
        OLG_BEGIN, "",
        "| pair | median | p95 | max | share over the display resolution |",
        "|---|---|---|---|---|",
    ]
    for key in ("unweighted", "weighted"):
        s_ = doc[key]
        bold = "**" if key == "weighted" else ""
        lines.append(
            f"| {key} | {s_['median']} | {s_['p95']} | {bold}{s_['max']}{bold} | "
            f"{bold}{s_['share_over_display_resolution'] * 100:.1f}%{bold} |"
        )
    lines += [
        "",
        f"{doc['candidates']} candidates across {doc['queries']} queries. The interface "
        f"prints rates to two significant figures, so a gap under {doc['display_resolution']} "
        "cannot move a displayed digit; the unweighted pair never exceeds the response's "
        # Not printed as a figure. It is a five-decimal constant, the number guard's forms
        # stop at four, and the project's own display rule is two significant figures --
        # so a number that cannot be checked and should not be shown is described instead.
        "own rounding at four decimals, and the weighted pair can move a "
        f"digit on {doc['weighted']['share_over_display_resolution'] * 100:.1f}% of "
        f"candidates by at most {doc['weighted']['max']}.",
        "",
        OLG_END,
    ]
    # The first line is not indented: the pattern matches from the marker, so the marker's
    # own leading whitespace stays in the document. Prefixing it too added the indent on
    # every regeneration -- four spaces, then eight, then twelve -- and eight spaces inside
    # a list item is a code fence, so the table rendered as literal text.
    return ("\n" + indent).join(lines).replace("\n" + indent + "\n", "\n\n")


def build_across_agent_trend_block(doc: dict, indent: str = "") -> str | None:
    """Two metrics, one expansion, opposite directions -- from artifacts/across_agent_trend.json.

    The block is generated rather than written because every one of its figures is the kind
    that moves under a refit, and because two of them are traps. The strongest across-agent
    number in the series belongs to a fit that failed its seed-agreement check, so the table
    has to carry convergence in the same row as the figure; and a positive mean whose
    interval excludes zero is still not support when the bar was declared at +0.3, so the
    verdict column has three values rather than two.
    """
    rows = [r for r in (doc.get("corpora") or []) if r.get("status") == "present"]
    if not rows:
        return None
    thr = doc.get("support_threshold")
    split = "leave_one_agent_out"
    carriers = [
        r for r in rows
        if (r["splits"].get(split, {}).get("across_agent", {}) or {}).get("applicable")
    ]
    if not carriers:
        return None
    carriers.sort(key=lambda r: r["n_agents"])
    lines = [
        AAT_BEGIN, "",
        "| corpus | agents | identification | censored | within-arm dAUC | "
        "across-agent rho | 95% CI | adjusted | reading |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in carriers:
        e = r["splits"][split]
        aa = e["across_agent"]
        name = r["corpus"]
        if not r["converged"]:
            name += " *(did not converge)*"
        if not r.get("on_expansion_path"):
            name += " *(off the expansion path)*"
        lines.append(
            f"| {name} | {r['n_agents']} | {r['identification_ratio']:.2f}:1 | "
            f"{r['censored_share'] * 100:.1f}% | "
            f"{e['delta_auc_mean']:+.4f} | {aa['model_mean']:+.4f} | "
            f"[{aa['model_ci'][0]:+.3f}, {aa['model_ci'][1]:+.3f}] | "
            # Section 5f's headline, which is computed from leave-one-agent-out fold
            # predictions and therefore belongs in no other split's table.
            + (f"{r['adjusted']['mean']:+.4f}"
               if (r.get("adjusted") and split == "leave_one_agent_out") else "--")
            + f" | {aa['verdict']} |"
        )
    lines.append("")
    tr = (doc.get("trends") or {}).get(split) or {}
    if not tr.get("computed"):
        pts = tr.get("points") or []
        lines.append(
            "**There is no trend to report**: "
            + f"{tr.get('reason', 'not computed')}."
            + (" The qualifying fits are "
               + ", ".join(f"{p['n_agents']} agents at {p['across_agent']:+.4f}"
                           for p in pts)
               + "." if pts else "")
        )
        lines.append("")
    if tr.get("computed"):
        lines.append(
            f"Over the {tr['n_points']} converged fits the two metrics move in "
            f"{'opposite' if tr['opposite_directions'] else 'the same'} directions: "
            f"across-agent rho against corpus size "
            f"{tr['across_agent_vs_corpus_size']['rho']:+.3f}"
            + (f" (p = {tr['across_agent_vs_corpus_size']['p']:.4f})"
               if tr["across_agent_vs_corpus_size"].get("p") is not None else "")
            + f", within-arm delta AUC against corpus size "
            f"{tr['delta_auc_vs_corpus_size']['rho']:+.3f}"
            + (f" (p = {tr['delta_auc_vs_corpus_size']['p']:.4f})"
               if tr["delta_auc_vs_corpus_size"].get("p") is not None else "")
            + f". {tr['note']}"
        )
        lines.append("")
        adj_tr = tr.get("adjusted_vs_corpus_size") or {}
        if adj_tr.get("rho") is not None:
            sig = [r for r in carriers
                   if (r.get("adjusted") or {}).get("significant")
                   and r["converged"] and r.get("on_expansion_path")]
            lines.append(
                "Section 5f's adjusted headline over the same fits gives rho "
                f"{adj_tr['rho']:+.3f} on {adj_tr['n_points']} points -- "
                + ", ".join(f"{p['n_agents']} agents at {p['adjusted']:+.4f}"
                            for p in adj_tr.get("points", []))
                + ". It moves with the unadjusted figure rather than against it."
            )
            lines.append("")
            if sig:
                insig = [r for r in carriers
                         if r.get("adjusted") and not r["adjusted"]["significant"]]
                lines.append(
                    "**On its own declared criterion it is a result on the larger "
                    "corpora.** That criterion is not the +0.3 bar above, which was "
                    "declared for the unadjusted out-of-fold figure: it is the "
                    "permutation test this artefact's verdict function has applied since "
                    "before it had anything to report -- p below 0.05 with a bootstrap "
                    f"interval excluding zero -- and **{len(sig)} of the five fits** now "
                    "read *A result*: "
                    + "; ".join(
                        f"{r['corpus']} at {r['adjusted']['mean']:+.4f}, "
                        f"[{r['adjusted']['ci'][0]:+.3f}, {r['adjusted']['ci'][1]:+.3f}], "
                        # A permutation p of 0.0000 is a formatting artefact of a finite
                        # number of shuffles, not a p-value. Printed as a bound.
                        + ("permutation p < 0.0001"
                           if r["adjusted"]["permutation_p"] < 1e-4 else
                           f"permutation p = {r['adjusted']['permutation_p']:.4f}")
                        for r in sig
                    )
                    + "."
                )
                lines.append("")
                lines.append(
                    "Section 5f's own objection to its old result was that the estimate "
                    "was smaller than the spread across the five ways of estimating the "
                    "adjustment. That is no longer the case where it is significant: the "
                    "spread is "
                    + " and ".join(
                        f"{r['adjusted']['estimator_spread']:.4f} on {r['corpus']}"
                        for r in sig
                    )
                    + ", against "
                    + " and ".join(
                        f"{r['adjusted']['estimator_spread']:.4f} on {r['corpus']}"
                        for r in insig
                    )
                    + " where it is not. The estimate grows and the estimator choice "
                    "stops mattering, which is what section 5f said a real effect would "
                    "do and what its sixteen-to-twenty-two pair did not."
                )
                lines.append("")
    # Keyed by split, because the figure quoted here has to be the one in the table
    # above it. An earlier version read a single slot that the producing script
    # overwrote per split, and printed the family split's +0.0163 under the agent
    # split's table.
    flagged = (doc.get("strongest_figure_from_a_nonconverged_fit_by_split") or {}).get(split)
    if flagged:
        lines.append(
            f"The largest across-agent figure in the table, {flagged['model_mean']:+.4f} "
            f"on {flagged['corpus']}, is **not quotable**: that fit's worst standardised "
            f"seed gap is {flagged['worst_seed_gap']:.4f} against a 0.3 threshold. It is "
            "the most attractive number this project has produced and it comes from the "
            "one fit that failed its own convergence check."
        )
        lines.append("")
    pred = doc.get("prediction") or {}
    if pred.get("made"):
        if pred.get("outcome"):
            obs = pred.get("observed") or {}
            lines.append(
                f"Prediction recorded before the merged fit landed -- *{pred['made']}* -- "
                f"**{pred['outcome']}**"
                + (f" (observed {obs['model_mean']:+.4f}, CI "
                   f"[{obs['model_ci'][0]:+.3f}, {obs['model_ci'][1]:+.3f}])."
                   if obs else ".")
            )
        else:
            lines.append(
                f"Prediction recorded, not yet scorable: *{pred['made']}*. "
                f"Pending: {', '.join(doc.get('pending') or []) or 'nothing'}."
            )
        lines.append("")
    onpath = [r for r in carriers if r["converged"] and r.get("on_expansion_path")]
    positive = [
        r for r in onpath
        if r["splits"][split]["across_agent"]["verdict"].startswith("positive")
    ]
    if thr is not None:
        clears = [
            r for r in carriers
            if r["converged"] and not r.get("superseded")
            and r["splits"][split]["across_agent"]["verdict"] == "supports the claim"
        ]
        lines.append(
            f"The bar was declared at +{thr} before the metric was first computed, and "
            + ("no row clears it." if not clears else
               f"{len(clears)} row(s) clear it: "
               + ", ".join(r["corpus"] for r in clears) + ".")
            + (
                f" {len(positive)} of the {len(onpath)} on-path converged rows read "
                "*positive, excludes zero, below the declared bar* and the rest read "
                "*indistinguishable from zero*, so the unadjusted series carries a "
                "direction plus two intervals clear of zero: the comparison the product "
                "makes moving up as the corpus grows while the pre-specified one moves "
                "down."
                if tr.get("computed") else
                " Without a trend, what the table shows is two quotable fits whose "
                "across-agent figures differ by 0.06 with overlapping intervals, and one "
                "unquotable fit that looks better than both. That is a reason to finish "
                "the pending fits, not a result."
            )
        )
        lines.append("")
    lines.append(AAT_END)
    # See build_objective_label_gap_block: the first line carries no indent.
    return ("\n" + indent).join(lines).replace("\n" + indent + "\n", "\n\n")


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
    ap.add_argument("--corpus-ablation", type=Path,
                    default=Path("artifacts/corpus_ablation.json"))
    ap.add_argument("--rank-resolution", type=Path,
                    default=Path("artifacts/rank_resolution.json"))
    ap.add_argument("--payload-compression", type=Path,
                    default=Path("artifacts/payload_axis_compression.json"))
    ap.add_argument("--source-axis", type=Path,
                    default=Path("artifacts/source_axis_heterogeneity.json"))
    ap.add_argument("--across-agent-trend", type=Path,
                    default=Path("artifacts/across_agent_trend.json"))
    ap.add_argument("--objective-label-gap", type=Path,
                    default=Path("artifacts/objective_label_gap.json"))
    ap.add_argument("--inverse-retrieval", type=Path,
                    default=Path("artifacts/inverse_retrieval.json"))
    ap.add_argument("--rank1", type=Path,
                    default=Path("artifacts/rank1_factorisation.json"))
    ap.add_argument("--threshold-accuracy", type=Path,
                    default=Path("artifacts/threshold_estimator_accuracy.json"))
    ap.add_argument("--posterior-choice", type=Path,
                    default=Path("artifacts/posterior_choice.json"))
    ap.add_argument("--across-agent-adjusted", type=Path,
                    default=Path("artifacts/across_agent_adjusted.json"))
    ap.add_argument("--axis-composition", type=Path,
                    default=Path("artifacts/axis_composition.json"))
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
    abl_block = (
        build_ablation_block(
            json.loads(args.corpus_ablation.read_text(encoding="utf-8"))
        )
        if args.corpus_ablation.exists() else None
    )
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
    aat_doc = (
        json.loads(args.across_agent_trend.read_text(encoding="utf-8"))
        if args.across_agent_trend.exists() else None
    )
    olg_doc = (
        json.loads(args.objective_label_gap.read_text(encoding="utf-8"))
        if args.objective_label_gap.exists() else None
    )
    inv_doc = (
        json.loads(args.inverse_retrieval.read_text(encoding="utf-8"))
        if args.inverse_retrieval.exists() else None
    )
    r1_doc = (
        json.loads(args.rank1.read_text(encoding="utf-8"))
        if args.rank1.exists() else None
    )
    tha_doc = (
        json.loads(args.threshold_accuracy.read_text(encoding="utf-8"))
        if args.threshold_accuracy.exists() else None
    )
    pch_doc = (
        json.loads(args.posterior_choice.read_text(encoding="utf-8"))
        if args.posterior_choice.exists() else None
    )
    aax_doc = (
        json.loads(args.across_agent_adjusted.read_text(encoding="utf-8"))
        if args.across_agent_adjusted.exists() else None
    )
    comp_doc = (
        json.loads(args.axis_composition.read_text(encoding="utf-8"))
        if args.axis_composition.exists() else None
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
    aat_pattern = re.compile(re.escape(AAT_BEGIN) + r".*?" + re.escape(AAT_END), re.S)
    olg_pattern = re.compile(re.escape(OLG_BEGIN) + r".*?" + re.escape(OLG_END), re.S)
    aax_pattern = re.compile(re.escape(AAX_BEGIN) + r".*?" + re.escape(AAX_END), re.S)
    pch_pattern = re.compile(re.escape(PCH_BEGIN) + r".*?" + re.escape(PCH_END), re.S)
    r1_pattern = re.compile(re.escape(R1_BEGIN) + r".*?" + re.escape(R1_END), re.S)
    inv_pattern = re.compile(re.escape(INV_BEGIN) + r".*?" + re.escape(INV_END), re.S)
    tha_pattern = re.compile(re.escape(THA_BEGIN) + r".*?" + re.escape(THA_END), re.S)
    abl_pattern = re.compile(re.escape(ABL_BEGIN) + r".*?" + re.escape(ABL_END), re.S)
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
        if abl_block and abl_pattern.search(text):
            replaced = abl_pattern.sub(lambda _: abl_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: corpus-ablation block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: corpus-ablation block regenerated")
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
        # `rx` and `made`, not `pattern` and `block`. Both of those names are used after
        # this loop by the fitted-parameters substitution, which is the oldest block in
        # this script: `pattern` is its regex and `block` is its text. Binding either as a
        # loop variable here left them pointing at the last entry in the tuple below.
        #
        # Both happened, in that order. First `pattern` made the model card report "has no
        # generated block" while carrying twelve of them. Then `block` did worse than
        # report: `pattern.sub(lambda _: block, text)` wrote the threshold-accuracy table
        # over the model card's fitted-parameter list, deleting nine paragraphs of
        # parameter interpretation and leaving a table about reporting cuts under the
        # heading "Calibration and uncertainty". Caught by `git diff`, which is the only
        # reason this is recoverable -- a name holding a different quantity, twice, in the
        # generator for the section about names holding different quantities.
        for name, builder, source, rx, begin in (
            ("inverse-retrieval", build_inverse_retrieval_block, inv_doc,
             inv_pattern, INV_BEGIN),
            ("rank1", build_rank1_block, r1_doc, r1_pattern, R1_BEGIN),
            ("threshold-accuracy", build_threshold_accuracy_block, tha_doc,
             tha_pattern, THA_BEGIN),
        ):
            made = builder(source, indent=_marker_indent(text, begin)) if source else None
            if made and rx.search(text):
                replaced = rx.sub(lambda _, b=made: b, text)
                if replaced != text:
                    if args.check:
                        print(f"{doc}: {name} block is STALE")
                        rc = 1
                    else:
                        text = replaced
                        doc.write_text(text, encoding="utf-8")
                        print(f"{doc}: {name} block regenerated")
        pch_block = (
            build_posterior_choice_block(
                pch_doc, indent=_marker_indent(text, PCH_BEGIN)
            )
            if pch_doc else None
        )
        if pch_block and pch_pattern.search(text):
            replaced = pch_pattern.sub(lambda _: pch_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: posterior-choice block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: posterior-choice block regenerated")
        aax_block = (
            build_across_agent_per_axis_block(
                aax_doc, comp_doc, indent=_marker_indent(text, AAX_BEGIN)
            )
            if aax_doc else None
        )
        if aax_block and aax_pattern.search(text):
            replaced = aax_pattern.sub(lambda _: aax_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: across-agent-per-axis block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: across-agent-per-axis block regenerated")
        olg_block = (
            build_objective_label_gap_block(
                olg_doc, indent=_marker_indent(text, OLG_BEGIN)
            )
            if olg_doc else None
        )
        if olg_block and olg_pattern.search(text):
            replaced = olg_pattern.sub(lambda _: olg_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: objective-label-gap block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: objective-label-gap block regenerated")
        aat_block = (
            build_across_agent_trend_block(
                aat_doc, indent=_marker_indent(text, AAT_BEGIN)
            )
            if aat_doc else None
        )
        if aat_block and aat_pattern.search(text):
            replaced = aat_pattern.sub(lambda _: aat_block, text)
            if replaced != text:
                if args.check:
                    print(f"{doc}: across-agent-trend block is STALE")
                    rc = 1
                else:
                    text = replaced
                    doc.write_text(text, encoding="utf-8")
                    print(f"{doc}: across-agent-trend block regenerated")
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
