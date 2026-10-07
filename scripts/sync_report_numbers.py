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

RES_BEGIN = "<!-- generated: results-table -->"
RES_END = "<!-- /generated: results-table -->"

CENS_ROWS = [
    ("censored", "censored"),
    ("zero_imputed", "zero-imputed"),
    ("threshold_0_only", "completely-reported subset only"),
]

# parameter -> (source, sentence). `{v}` is substituted with "mean [q05, q95]".
NOTES: dict[str, tuple[str, str]] = {
    "tau_cleav": (
        "tau_cleav",
        "the scale of the cleavable-versus-non-cleavable linker contrast across axes. "
        "Clear of zero, and about half the size of the mechanism scale -- so linker "
        "cleavability shifts the organ profile, and shifts it less than the payload "
        "mechanism does. This is the one design axis the corpus identifies comfortably: "
        "cleavability is binary and needs only 8 agents to estimate, against the 40 a "
        "mechanism level needs and the 80 a payload level would.",
    ),
    "tau_mech": (
        "tau_mech",
        "the mechanism x axis interaction is supported by the data rather than asserted "
        "by a parameter count.",
    ),
    "sigma_agent": (
        "coefficients",
        "small, so the design slots account for much of the between-agent variation.",
    ),
    "b_combo": ("coefficients", "combination arms do report higher rates."),
    "b_log_n": (
        "coefficients",
        "an ascertainment effect that would have been attributed to the design had it not "
        "been controlled.",
    ),
    "b_dar": (
        "coefficients",
        "includes zero. DAR is an agent-level constant and is confounded with agent "
        "identity here. The pharmacokinetic literature supports a DAR effect; this corpus "
        "does not resolve one.",
    ),
    "b_thresh": (
        "coefficients",
        "the reporting-threshold covariate. Not the censoring correction: it is four times "
        "larger on the seriousEvents table, which has no censored cells at all, so it is "
        "substantially absorbing trial-level reporting practice.",
    ),
}


def _fmt(cell: dict, signed: bool) -> str:
    """Four decimals, so check_report.py has power on these figures.

    `signed` is False for scale parameters: tau and sigma are positive by construction, so
    a leading "+" on them implies a sign that could have gone the other way.
    """
    if not signed:
        return f"{cell['mean']:.4f} [{cell['q05']:.4f}, {cell['q95']:.4f}]"
    return f"{cell['mean']:+.4f} [{cell['q05']:+.4f}, {cell['q95']:+.4f}]"


def build_block(metrics: dict) -> str:
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
        lines.append(f"`{name}` {_fmt(cell, signed)} -- {note}")
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
    ap.add_argument("--check", action="store_true",
                    help="fail if the block is out of date instead of rewriting it")
    args = ap.parse_args()

    if not args.metrics.exists():
        print(f"{args.metrics} absent; run `make forward` first")
        return 1
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    block = build_block(metrics)

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
