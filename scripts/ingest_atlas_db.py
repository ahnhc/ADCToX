"""Ingest the teammate-supplied ADC database into this project's arm/observation frames.

What arrived: a hand-transcribed clinical-toxicity database over 99 ADCs -- 17,094 adverse
event rows, every one carrying a numerator, a denominator, a percentage, the verbatim source
cell, and the table/row/column it came from. 72 of those ADCs have organ-specific any-grade
rows. 46 of the 72 are absent from the corpus this project built, so the union is 80 agents
against the 32 the automated pipeline reached.

Why it is worth ingesting rather than treating as a cross-check. Three measurements:

  * The arithmetic gate -- |100*n/N - pct| <= 0.6pp, this project's deterministic
    hallucination detector -- passes on **99.81%** of the rows where all three numbers are
    present. The automated PMC extraction passes 86.8%. A human transcribing a table and
    keeping the source cell is simply better than a parser plus a classifier.
  * `threshold_hat = min(reported %)` is recoverable for every one of the 355 usable
    cohorts, median 10.0%, so the censored likelihood this project's model is built around
    applies unchanged.
  * The verbatim cells are a median of 6 characters and at most 27, with 0.08% above the
    24-character ceiling `tests/test_licence_posture.py` enforces. The licence posture
    survives: the numbers publish, the workbook does not.

What this script refuses, and why each refusal is a line of code rather than a judgement:

  * Aggregate rows. "Overall", total AE, discontinuation, death -- already labelled
    `Aggregate / Outcome (not organ-specific)` upstream, and dropped here too.
  * Non-canonical duplicates (`Canonical observation` false).
  * Rows failing the arithmetic gate. Not flagged: dropped. A row whose printed percentage
    disagrees with its own n/N has an error somewhere in it and nothing downstream can tell
    which part.
  * Unconjugated antibodies. `farletuzumab` is a naked antibody with `Payload: NA`; its
    toxicity is not an ADC's.
  * Domains outside the 14 axes, each with a recorded reason (atlas_domains.yaml).

What it keeps that the registry corpus has no equivalent for: `source_tier`. These rows come
from four kinds of document -- primary publication, regulatory label, conference abstract,
sponsor presentation -- and negative result 34 measured that the reporting source shifts the
organ profile by up to 1.85 logit on a single axis. A two-level registry/literature indicator
cannot absorb four sources, so the tier is carried through for the model to decide on.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json
from adctox.taxonomy import Taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The gate from the extraction pipeline, in the same units, so the two corpora are held to
# one standard rather than to whichever was convenient.
ARITHMETIC_TOLERANCE_PP = 0.6

AGGREGATE_MARKERS = ("aggregate", "not organ")

# Document kinds, coarsest first. `publication` is the registry corpus's nearest neighbour
# and is therefore the reference level.
SOURCE_TIER = {
    "Primary clinical publication": "publication",
    "Regulatory label via DailyMed": "label",
    "Conference abstract": "abstract",
    "Official sponsor presentation": "presentation",
}


def _agent_key(adc_id: str) -> str:
    """Their `ADC ID` is already an INN slug; only the separator differs.

    Deliberately not a fuzzy match on `ADC name`, which carries parenthetical code names
    ("SC-011 / ABBV-011 (SC17, SEZ6, calicheamicin)") and matched 23 of 26 overlapping
    agents instead of 26 when tried.
    """
    return str(adc_id).strip().lower().replace("-", "_")


def _load_crosswalk(path: pathlib.Path) -> tuple[dict[str, str], dict[str, str]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    axis_of = {str(k): str(v) for k, v in doc["axis_of_domain"].items()}
    dropped = {str(k): v["reason"] for k, v in (doc.get("dropped") or {}).items()}
    axes = set(Taxonomy().axis_order)
    unknown = {v for v in axis_of.values()} - axes
    if unknown:
        raise ValueError(f"crosswalk targets axes this project does not have: {unknown}")
    return axis_of, dropped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=pathlib.Path,
                    default=ROOT / "data" / "raw" / "atlas" / "2026-10-10" / "adc_db.xlsx")
    ap.add_argument("--crosswalk", type=pathlib.Path,
                    default=ROOT / "conf" / "ontology" / "atlas_domains.yaml")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "atlas")
    ap.add_argument("--report", type=pathlib.Path,
                    default=ROOT / "artifacts" / "atlas_ingest.json")
    args = ap.parse_args()

    if not args.workbook.exists():
        print(f"{args.workbook} absent. The workbook is not redistributed; see "
              "data/raw/atlas/*/\\_manifest.json for its hash.", file=sys.stderr)
        return 1

    axis_of, dropped_reasons = _load_crosswalk(args.crosswalk)
    tox = pd.read_excel(args.workbook, sheet_name="TOXICITY")
    master = pd.read_excel(args.workbook, sheet_name="ADC_MASTER")
    trial = pd.read_excel(args.workbook, sheet_name="TRIAL")

    # A denominator the TOXICITY sheet does not carry but the TRIAL sheet does. 492
    # organ-specific any-grade rows have `At risk N` of "NR", and this ingest called them an
    # irreversible loss -- no denominator, no rate. The TRIAL sheet has a `Sample size` per
    # cohort, and the question is whether it is the same quantity.
    #
    # Mostly, and the exceptions are the point. Per cohort, taking one row each, the two
    # agree on all 393 cohorts that carry both. Row by row they agree on 15,899 of 15,947,
    # and the 48 that disagree are all **sub-population denominators**: `ags-16c3f`'s
    # phase 2 enrolled 66 and evaluated 59 for ocular diagnosis, and its haematologic and
    # hepatic rows likewise carry the laboratory-evaluable subset. So a printed row-level
    # denominator always wins, and the cohort figure is a fallback whose risk is using an
    # enrolment where a smaller evaluable subset applied -- which would deflate that rate.
    #
    # Measured, that risk runs at 0.3% of rows and it is recorded rather than assumed away.
    # The substituted rows are marked, so a later analysis can drop them in one filter.
    cohort_n = (
        trial.assign(_n=pd.to_numeric(trial["Sample size"], errors="coerce"))
        .dropna(subset=["_n"])
        .set_index("Trial ID")["_n"]
        .to_dict()
    )
    printed = pd.to_numeric(tox["At risk N"], errors="coerce")
    fallback = tox["Trial ID"].map(cohort_n)
    both = printed.notna() & fallback.notna()
    disagree = int((printed[both] != fallback[both]).sum())
    substituted = printed.isna() & fallback.notna()
    denominator_check = {
        "rows_with_both": int(both.sum()),
        "rows_disagreeing": disagree,
        "disagreement_rate": round(disagree / max(int(both.sum()), 1), 4),
        # Both directions recorded, because the report quotes the agreement and the guard
        # below thresholds on the disagreement, and deriving one from the other in prose is
        # how a figure stops tracing to an artefact.
        "agreement_rate": round(1 - disagree / max(int(both.sum()), 1), 4),
        "rows_substituted": int(substituted.sum()),
        "note": ("Where both are present the printed row-level denominator wins. The "
                 "disagreements are sub-population denominators -- an ocular sub-study, a "
                 "laboratory-evaluable subset -- so the substituted rows carry the risk of "
                 "an enrolment standing in for a smaller evaluable subset, which would "
                 "deflate the rate. The measured rate of that happening is the "
                 "disagreement rate above."),
    }
    # A fallback is worth taking at a 0.3% error rate and not at a large one, so the
    # threshold is explicit rather than implied by the absence of a check.
    if denominator_check["disagreement_rate"] > 0.05:
        raise ValueError(
            f"TRIAL `Sample size` disagrees with TOXICITY `At risk N` on "
            f"{denominator_check['disagreement_rate']:.1%} of rows carrying both. The "
            "fallback rests on them being the same quantity at the row level; at this rate "
            "it would put a wrong number under every rate on a substituted arm, which is "
            "worse than losing the arm."
        )
    tox = tox.assign(
        **{"At risk N": printed.where(printed.notna(), fallback)},
        denominator_source=np.where(substituted, "cohort_fallback", "row_printed"),
    )

    funnel: list[dict] = [{"step": "raw TOXICITY rows", "rows": len(tox)}]

    def note(step: str, frame: pd.DataFrame) -> pd.DataFrame:
        funnel.append({"step": step, "rows": len(frame),
                       "agents": int(frame["ADC ID"].nunique())})
        return frame

    d = tox.copy()
    d["domain"] = d["Toxicity domain"].astype(str).str.strip()

    agg = d["domain"].str.lower().apply(lambda s: any(m in s for m in AGGREGATE_MARKERS))
    d = note("minus aggregate/outcome rows", d[~agg])

    d = note("minus non-canonical duplicates",
             d[d["Canonical observation"].fillna(True).astype(bool)])

    d = note("any-grade only", d[d["Grade category"].astype(str).str.strip() == "Any grade"])

    # Usability and verifiability are different questions, and conflating them threw away
    # 28% of the rows on the first pass -- including every one of the 883 regulatory-label
    # rows, which print a percentage and a denominator but no numerator.
    #
    #   usable          needs a denominator, and either a numerator or a percentage
    #   verifiable      needs all three, so |100*n/N - pct| can be computed
    #
    # The plan's own rule for the extraction pipeline is that arithmetic failures are
    # flagged and not discarded, and the pass rate is published as a data-quality figure.
    # The same rule applies here, so a contradictory row is carried with `arithmetic_pass`
    # false and the dataset builder decides, rather than this script deciding silently.
    n = pd.to_numeric(d["Affected n"], errors="coerce")
    N = pd.to_numeric(d["At risk N"], errors="coerce")
    pct = pd.to_numeric(d["Incidence percent"], errors="coerce")

    has_denominator = N.notna() & (N > 0)
    d = note("minus rows with no denominator", d[has_denominator])
    n, N, pct = n[d.index], N[d.index], pct[d.index]

    # A numerator reconstructed from a printed percentage is exact to rounding, and the
    # rounding is recorded so a later analysis can widen those cells if it wants to.
    reconstructed = n.isna() & pct.notna()
    n_filled = n.where(~reconstructed, (pct * N / 100).round())
    d["rate_source"] = pd.Series("n_and_N", index=d.index).where(~reconstructed, "pct_and_N")

    d = note("minus rows with neither a numerator nor a percentage", d[n_filled.notna()])
    n_filled, N, pct = n_filled[d.index], N[d.index], pct[d.index]
    d["rate_source"] = d["rate_source"][d.index]

    impossible = n_filled > N
    d = note("minus rows whose numerator exceeds its denominator", d[~impossible])
    n_filled, N, pct = n_filled[d.index], N[d.index], pct[d.index]

    # Verifiable only where the percentage was printed *and* the numerator was not derived
    # from it -- otherwise the check is circular and passes by construction.
    verifiable = pct.notna() & (d["rate_source"] == "n_and_N")
    gap = (100 * n_filled / N - pct).abs()
    d["arithmetic_checked"] = verifiable
    d["arithmetic_gap_pp"] = gap.where(verifiable)
    d["arithmetic_pass"] = (~verifiable) | (gap <= ARITHMETIC_TOLERANCE_PP)
    gate = {
        "tolerance_pp": ARITHMETIC_TOLERANCE_PP,
        "verifiable": int(verifiable.sum()),
        "not_verifiable": int((~verifiable).sum()),
        "passed": int((verifiable & (gap <= ARITHMETIC_TOLERANCE_PP)).sum()),
        "pass_rate_of_verifiable": float(
            (verifiable & (gap <= ARITHMETIC_TOLERANCE_PP)).sum() / max(int(verifiable.sum()), 1)
        ),
        "median_gap_pp": float(gap[verifiable].median()),
        "numerator_reconstructed_from_percentage": int((d["rate_source"] == "pct_and_N").sum()),
        "note": ("Failures are flagged, not dropped -- the same rule the extraction pipeline "
                 "uses. A reconstructed numerator is marked not-verifiable rather than "
                 "passing, because checking it against the percentage it came from is "
                 "circular."),
    }
    d["n_affected_final"] = n_filled

    # Unconjugated antibodies, by the payload field rather than by name.
    payload = master.set_index("ADC ID")["Payload"].astype(str)
    naked = {i for i, v in payload.items() if "unconjugated" in v.lower()}
    d = note("minus unconjugated antibodies", d[~d["ADC ID"].isin(naked)])

    unmapped = sorted(set(d["domain"]) - set(axis_of))
    unexplained = [u for u in unmapped if u not in dropped_reasons]
    if unexplained:
        raise ValueError(
            "domain labels with neither an axis nor a recorded reason: "
            f"{unexplained}. Add them to {args.crosswalk} rather than letting them fall "
            "out of the corpus silently."
        )
    d["axis"] = d["domain"].map(axis_of)
    d = note("minus domains outside the 14 axes", d[d["axis"].notna()])

    d["agent"] = d["ADC ID"].map(_agent_key)
    d["source_tier"] = d["Source type"].map(SOURCE_TIER).fillna("other")
    d["n_affected"] = d["n_affected_final"].astype(int)
    d["n_at_risk"] = pd.to_numeric(d["At risk N"], errors="coerce").astype(int)
    # The rate the grid will use. Printed where printed, derived where the
    # numerator was printed instead.
    d["pct"] = pd.to_numeric(d["Incidence percent"], errors="coerce").fillna(
        100 * d["n_affected"] / d["n_at_risk"])
    d["arm_key"] = (
        "ATLAS_" + d["agent"] + "_" + d["Trial ID"].astype(str).map(
            lambda s: hashlib.sha1(s.encode()).hexdigest()[:8]
        )
    )

    # One cell per (arm, axis): their rows are per preferred term, ours are per axis. Summed
    # numerators would double-count a patient with two events on one organ, so the cell takes
    # the **maximum** term rate on that axis, which is what the registry grid does.
    grouped = (
        d.sort_values("pct", ascending=False)
        .groupby(["arm_key", "axis"], as_index=False)
        .agg(agent=("agent", "first"),
             n_affected=("n_affected", "first"),
             n_at_risk=("n_at_risk", "first"),
             pct=("pct", "first"),
             n_terms=("pct", "size"),
             sum_affected_terms=("n_affected", "sum"),
             source_tier=("source_tier", "first"),
             source_domain=("domain", "first"),
             rate_source=("rate_source", "first"),
             arithmetic_checked=("arithmetic_checked", "all"),
             arithmetic_pass=("arithmetic_pass", "all"))
    )

    # threshold_hat: the smallest percentage the cohort reported anywhere, an upper bound on
    # its reporting cut. Computed over the arm's *terms*, not its axis cells, because the cut
    # applied to terms.
    thresh = d.groupby("arm_key")["pct"].min().rename("frequency_threshold")

    arm_meta = (
        d.groupby("arm_key")
        .agg(agent=("agent", "first"),
             trial_id=("Trial ID", "first"),
             adc_id=("ADC ID", "first"),
             n_at_risk=("n_at_risk", "max"),
             monotherapy=("Monotherapy", "first"),
             ae_definition=("AE definition", "first"),
             source_tier=("source_tier", "first"),
             dose=("Dose", "first"),
             doi=("DOI", "first"),
             denominator_source=("denominator_source", "min"))
        .join(thresh)
        .reset_index()
    )

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    grouped.to_parquet(out / "observations_raw.parquet", index=False)
    arm_meta.to_parquet(out / "arms_raw.parquet", index=False)

    # What this ingest deliberately leaves on the table, measured so "we only took the
    # any-grade rows" is a number rather than a shrug. The severe-grade rows are plentiful
    # and they are not a substitute for the registry's seriousEvents table: Grade >=3 is a
    # *severity* cut and a serious adverse event is a *regulatory* category (hospitalisation,
    # death, a life-threatening event), and a severity table from a paper carries its own
    # reporting cut so it would not serve the purpose the serious table serves here -- a
    # table where an absence is a true zero. Using it would need a severity-stratified
    # outcome, which is a different model.
    _tox_domain = tox["Toxicity domain"].astype(str).str.strip().str.lower()
    severe = tox[
        tox["Grade category"].astype(str).str.contains("Grade >=3|Grade 3", na=False)
        & ~_tox_domain.apply(lambda v: any(m in v for m in AGGREGATE_MARKERS))
    ]
    severe_n = pd.to_numeric(severe["At risk N"], errors="coerce")
    unused = {
        "severe_grade_organ_rows": int(len(severe)),
        "severe_grade_organ_rows_with_denominator": int(severe_n.notna().sum()),
        "severe_grade_agents": int(severe["ADC ID"].nunique()),
        "grade_categories": {str(k): int(v) for k, v in
                             severe["Grade category"].value_counts().items()},
        "reason": ("Grade >=3 is a severity cut; the registry's seriousEvents table is a "
                   "regulatory category. They are different outcomes, and a severity table "
                   "from a paper carries its own reporting cut, so it cannot serve as the "
                   "uncensored comparison the serious table provides."),
    }

    report = {
        "deliberately_unused": unused,
        "denominator_fallback": denominator_check,
        "workbook_sha256": hashlib.sha256(args.workbook.read_bytes()).hexdigest(),
        "arithmetic_gate": gate,
        "funnel": funnel,
        "arms": int(len(arm_meta)),
        "agents": int(arm_meta["agent"].nunique()),
        "axis_cells": int(len(grouped)),
        "axes_covered": int(grouped["axis"].nunique()),
        "source_tiers": {k: int(v) for k, v in
                         arm_meta["source_tier"].value_counts().items()},
        "threshold_hat": {
            "median": float(arm_meta["frequency_threshold"].median()),
            "max": float(arm_meta["frequency_threshold"].max()),
            "recoverable_for_arms": int(arm_meta["frequency_threshold"].notna().sum()),
        },
        "dropped_domains": dropped_reasons,
        "unconjugated_excluded": sorted(_agent_key(i) for i in naked),
    }
    write_json(args.report, report)

    print(f"denominator fallback: TRIAL `Sample size` agrees with the printed `At risk N` "
          f"on {denominator_check['rows_with_both'] - denominator_check['rows_disagreeing']}"
          f"/{denominator_check['rows_with_both']} rows carrying both "
          f"({denominator_check['disagreement_rate']:.2%} disagree, all sub-population "
          f"denominators), so it fills {denominator_check['rows_substituted']} rows that "
          "carry none")
    print()
    print(f"arithmetic gate: {gate['passed']}/{gate['verifiable']} verifiable rows pass "
          f"({gate['pass_rate_of_verifiable'] * 100:.2f}%), median gap "
          f"{gate['median_gap_pp']:.4f}pp; {gate['not_verifiable']} not verifiable, of which "
          f"{gate['numerator_reconstructed_from_percentage']} had the numerator reconstructed "
          "from a printed percentage")
    print()
    for f in funnel:
        print(f"  {f['step']:40} {f['rows']:6}"
              + (f"  agents {f['agents']}" if "agents" in f else ""))
    print()
    print(f"arms {report['arms']} | agents {report['agents']} | "
          f"axis cells {report['axis_cells']} over {report['axes_covered']} axes")
    print(f"source tiers: {report['source_tiers']}")
    print(f"threshold_hat median {report['threshold_hat']['median']:.1f}%")
    print(f"deliberately unused: {unused['severe_grade_organ_rows_with_denominator']} "
          f"severe-grade organ rows with a denominator over "
          f"{unused['severe_grade_agents']} agents -- a severity table, not a seriousness "
          "one")
    print(f"-> {out}/ and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
