"""Two metrics, one corpus expansion, opposite directions.

Every corpus expansion has made the headline validation worse. Leave-one-mechanism-out
macro delta: -0.0200 on the registry corpus, -0.1613 at 32 agents, -0.121 at 65. Three
expansions, three steps backwards, and the identification ratio improving at every step
(3.08 -> 4.48 -> 9.10). That pairing is the project's central puzzle and the obvious
reading -- the added data is worse data -- has been the working assumption.

This script checks whether it is the whole reading, because the project measures a second
discrimination metric and the two are not asking the same question:

  within-arm AUC        rank the 14 axes INSIDE one held-out arm. A *constant* predictor,
                        the global axis mean, scores about 0.84 on it, because axis base
                        rates are consistent enough across arms that knowing them is
                        nearly the whole task. A design-blind constant wins this metric.

  across-agent Spearman for one axis, rank the held-out AGENTS. The global mean has zero
                        discriminative power here by construction, so the metric cannot
                        be won by a base rate.

The product's claim is the second comparison. A clinician choosing between two candidate
designs for a patient with kidney disease is asking which design carries less renal risk,
not which organ is this design's worst. So if the two metrics disagree about what the
expansions bought, the one that matches the product's question is the one to read -- and
the one that does not is the one to keep reporting anyway, because it was pre-specified.

The threshold was declared before the metric was first computed and is quoted here from
fit_forward.py rather than retyped, so the two cannot drift apart: a mean above +0.3 with
a bootstrap CI excluding zero supports the claim, anything at or below zero refutes it.
The interesting case is between -- distinguishable from zero and short of the bar -- and
this script is written to name that case rather than round it to a verdict.

One thing the trend table must carry, because it reverses a reading: a fit's figures are
only as good as its convergence, and the strongest across-agent number in the series may
come from a fit that failed its own seed-agreement check. The table marks it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.model import dataset as ds  # noqa: E402
from adctox.provenance import write_json  # noqa: E402
from adctox.taxonomy import default_taxonomy  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The declaration this script scores against, as a literal. If the sentence leaves
# fit_forward.py the script fails rather than scoring against a threshold nothing declares.
DECLARATION = (
    "a mean Spearman above +0.3 with a bootstrap CI excluding zero would support the "
    "claim; anything at or below zero refutes it"
)
SUPPORT_THRESHOLD = 0.3

# Ordered by corpus size, which is also the order the expansions happened in. Each entry
# carries the processed frames the fit read and whether it was run with
# `--drop-uninformative-absences`, because the agent set is what decides whether a fit is a
# point on the expansion path and the only way to know it is to load the corpus.
#
# Membership is computed, not declared. A corpus-size trend needs its points to be one
# corpus at different sizes, so the script builds the nesting chain from the registry
# baseline upwards and excludes any fit whose agent set is not a superset of the baseline's.
# One is: `artifacts/with_literature` reports 17 agents and is neither a subset nor a
# superset of the 22-agent registry -- it carries telisotuzumab_vedotin, which the registry
# grid does not, and lacks six that it does. Its "17" and the series' "22" are not two sizes
# of one thing, and a hand-maintained flag would have been one more thing to keep true.
CORPORA = [
    ("registry 22", "artifacts", "data/processed", False),
    ("literature 17", "artifacts/with_literature", "data/processed/with_literature", False),
    ("explicit cuts 26", "artifacts/with_explicit_threshold",
     "data/processed/with_explicit_threshold", False),
    ("expanded 32", "artifacts/with_literature_final",
     "data/processed/with_literature_final", False),
    ("expanded 32, absences dropped", "artifacts/with_literature_dropabs",
     "data/processed/with_literature_final", True),
    # Named for what it was built to be and not for what it is: restricting the 32-agent
    # corpus to the explicit-cuts agents and keeping every arm yields a 27-agent grid, not
    # a 26-agent one, because praluzatamab ravtansine's only arms are upper-bound and with
    # them it clears the grid's cell threshold. The label says 27.
    ("explicit agents 27, all arms", "artifacts/with_literature_26agents",
     "data/processed/with_literature_26agents", False),
    ("merged 65", "artifacts/with_atlas", "data/processed/with_atlas", False),
    ("merged 65, absences dropped", "artifacts/with_atlas_dropabs",
     "data/processed/with_atlas", True),
]

# The fit the chain is measured from. Every other corpus is on the path if its agent set
# contains this one's.
BASELINE = "registry 22"

SPLITS = ["leave_one_agent_out", "leave_one_family_out", "leave_one_mechanism_out"]


def _check_declaration() -> None:
    text = (ROOT / "scripts" / "fit_forward.py").read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", text)
    assert DECLARATION in flat, (
        "the pre-declared threshold sentence is no longer in fit_forward.py, so this "
        "script would be scoring against a bar nothing declares"
    )


def _mark_off_chain(rows: list[dict]) -> None:
    """Compute, per fit, whether its agent set contains the baseline's.

    Writes `on_expansion_path` and, where it is false, the agents that make it false. A fit
    off the path is read and printed and kept out of the trend: its agent count is not a
    larger value of the baseline's quantity, so putting the two on one axis labels a
    difference in composition as a difference in size.
    """
    base = next((r for r in rows if r["corpus"] == BASELINE), None)
    base_agents = None
    if base and base["status"] == "present":
        base_agents = _agents(base["processed"], base["drop_uninformative_absences"])
    for r in rows:
        if r["status"] != "present":
            continue
        if base_agents is None:
            r["on_expansion_path"] = None
            r["off_path_reason"] = f"the {BASELINE} frames are not on disk to compare against"
            continue
        mine = _agents(r["processed"], r["drop_uninformative_absences"])
        if mine is None:
            r["on_expansion_path"] = None
            r["off_path_reason"] = f"{r['processed']} is not on disk"
            continue
        # The fit's own metrics state an agent count. If the frames give a different one,
        # the frames have moved since the fit read them and nothing downstream is safe.
        if len(mine) != r["n_agents"]:
            r["on_expansion_path"] = None
            r["off_path_reason"] = (
                f"the fit recorded {r['n_agents']} agents and {r['processed']} now holds "
                f"{len(mine)}; the frames changed after the fit read them"
            )
            continue
        missing = sorted(base_agents - mine)
        r["on_expansion_path"] = not missing
        r["off_path_reason"] = (
            None if not missing else
            f"lacks {len(missing)} of the {BASELINE} grid's agents ({', '.join(missing)}) "
            f"and adds {len(mine - base_agents)} it does not carry, so it is neither a "
            "subset nor a superset of the baseline"
        )


def _verdict(mean: float, ci: list[float]) -> str:
    """Three outcomes, not two. The middle one is the one the series actually lands in."""
    if ci[0] <= 0 <= ci[1]:
        return "indistinguishable from zero"
    if ci[1] < 0:
        return "negative, excludes zero"
    if mean > SUPPORT_THRESHOLD:
        return "supports the claim"
    return "positive, excludes zero, below the declared bar"


def _agents(processed: str, drop: bool) -> set[str] | None:
    """The fit's agent grid, or None if the frames are not on disk."""
    path = ROOT / processed
    if not (path / "arms.parquet").exists():
        return None
    data = ds.load(path, list(default_taxonomy().axis_order), kind="other",
                   drop_uninformative_absences=drop)
    return set(data.agents)


def _read(label: str, art: str, processed: str, drop: bool) -> dict:
    path = ROOT / art / "forward_other_metrics.json"
    if not path.exists():
        return {"corpus": label, "status": "pending", "artefact": art,
                "processed": processed}
    d = json.loads(path.read_text(encoding="utf-8"))
    row: dict = {
        "corpus": label,
        "status": "present",
        "artefact": art,
        "processed": processed,
        "drop_uninformative_absences": drop,
        "n_agents": int(re.search(r"(\d+) agents", d["corpus"]).group(1)),
        "identification_ratio": d["parameters"]["design_ratio_vs_identifying"],
        "identifying_cells": d["parameters"]["identifying_cells"],
        # Printed in the table because the three on-path converged fits must be comparable
        # on something other than size: if the censored share moved with the agent count,
        # the series would be measuring the censoring treatment.
        "censored_share": round(
            int(re.search(r"([\d,]+) censored", d["corpus"]).group(1).replace(",", ""))
            / int(re.search(r"^([\d,]+) cells", d["corpus"]).group(1).replace(",", "")), 4
        ),
        "converged": bool(d["seed_agreement"]["converged"]),
        "worst_seed_gap": round(d["seed_agreement"]["worst_standardized_gap"], 4),
        "splits": {},
    }
    # Section 5f's headline is the ADJUSTED figure, which removes the between-agent
    # reporting conditions, and it is a separate artefact because it is a separate
    # computation. It has to sit in the table beside the unadjusted one: the unadjusted
    # series rises monotonically with corpus size and the adjusted series does not, so a
    # table carrying only the first would support a claim the project's own headline
    # quantity does not make.
    adj_path = ROOT / art / "across_agent_adjusted.json"
    if adj_path.exists():
        a = json.loads(adj_path.read_text(encoding="utf-8"))
        head = a.get("headline_variant")
        v = (a.get("variants") or {}).get(head) or {}
        if "mean_spearman" in v:
            pp = (a.get("permutation_p") or {}).get(head)
            ci = [round(x, 4) for x in v["ci"]]
            row["adjusted"] = {
                "variant": head,
                "mean": round(v["mean_spearman"], 4),
                "ci": ci,
                "permutation_p": pp,
                "n_agents": a.get("n_agents"),
                # The adjusted metric's own declared criterion, which is not the +0.3 bar:
                # that bar was declared for the unadjusted out-of-fold figure in
                # `fit_forward.py`. This one is the permutation test the artefact's verdict
                # function has always applied -- p < 0.05 with a bootstrap interval
                # excluding zero -- and the function was written when it said "No signal".
                "significant": bool(pp is not None and pp < 0.05 and ci[0] > 0),
                # How much the estimate moves across the five ways of removing the
                # reporting conditions. Section 5f's own objection to its old result was
                # that the estimate was smaller than this spread.
                "estimator_spread": round(max(
                    abs(vv["mean_spearman"] - v["mean_spearman"])
                    for vv in (a.get("variants") or {}).values()
                    if "mean_spearman" in vv
                ), 4),
                "verdict": (a.get("reading") or "").split(".")[0] + ".",
            }
            # The adjusted artefact records its own agent count. If it disagrees with the
            # fit's, one of the two was produced against a different corpus.
            assert a.get("n_agents") == row["n_agents"], (
                f"{adj_path} says {a.get('n_agents')} agents, the fit beside it says "
                f"{row['n_agents']}"
            )
    for split in SPLITS:
        cv = d["cv"].get(split)
        if not cv:
            continue
        entry: dict = {
            "delta_auc_mean": round(cv["delta_auc_mean"], 4),
            "delta_auc_ci": [round(x, 4) for x in cv["delta_auc_ci"]],
            "n_folds": len(cv["folds"]),
        }
        sp = cv.get("across_agent_spearman") or {}
        if sp.get("applicable") is False:
            entry["across_agent"] = {"applicable": False, "reason": sp.get("reason")}
        elif "model_mean" in sp:
            mean = round(sp["model_mean"], 4)
            ci = [round(x, 4) for x in sp["model_ci"]]
            entry["across_agent"] = {
                "applicable": True,
                "model_mean": mean,
                "model_ci": ci,
                "mech_baseline_mean": round(sp["mech_baseline_mean"], 4),
                "global_baseline_mean": round(sp["global_baseline_mean"], 4),
                "n_folds_contributing": sp["n_folds_contributing"],
                "verdict": _verdict(mean, ci),
            }
        row["splits"][split] = entry
    return row


def _trend(rows: list[dict], split: str) -> dict:
    """Do the two metrics move in opposite directions as the corpus grows?

    Measured on the converged fits only, and on whichever corpora have the split -- a
    rank correlation over four points is weak evidence and is reported as such, but the
    sign is the claim and the sign is what four points can carry.
    """
    import numpy as np
    from scipy import stats

    pts = []
    adj_pts = []
    for r in rows:
        if (r["status"] != "present" or not r["converged"]
                or not r.get("on_expansion_path")):
            continue
        e = r["splits"].get(split, {})
        aa = e.get("across_agent", {})
        if not aa.get("applicable"):
            continue
        pts.append((r["n_agents"], aa["model_mean"], e["delta_auc_mean"]))
        if r.get("adjusted"):
            adj_pts.append((r["n_agents"], r["adjusted"]["mean"]))
    adj_pts.sort()
    pts.sort()
    if len(pts) < 3:
        return {"computed": False, "n_points": len(pts),
                "points": [{"n_agents": int(a), "across_agent": float(b),
                            "delta_auc": float(c)} for a, b, c in pts],
                "reason": ("fewer than three converged fits on the expansion path carry "
                           "this split, and two points cannot carry a trend")}
    n = np.array([p[0] for p in pts], float)
    aa = np.array([p[1] for p in pts], float)
    auc = np.array([p[2] for p in pts], float)
    r_aa = stats.spearmanr(n, aa)
    r_auc = stats.spearmanr(n, auc)
    return {
        "computed": True,
        "n_points": len(pts),
        "points": [{"n_agents": int(a), "across_agent": float(b), "delta_auc": float(c)}
                   for a, b, c in pts],
        # No p-value below five points. A Spearman rho of 1.0 over three points returns
        # p = 0.0, which is an artefact of there being only six orderings and not evidence
        # of anything. A figure of 0.0 beside a rho of 1.0 would be the most quotable and
        # least meaningful number in this report.
        "across_agent_vs_corpus_size": (
            {"rho": round(float(r_aa.statistic), 4),
             "p": round(float(r_aa.pvalue), 4)} if len(pts) >= 5 else
            {"rho": round(float(r_aa.statistic), 4), "p": None,
             "p_withheld_because": f"{len(pts)} points; a p-value needs at least five"}
        ),
        "delta_auc_vs_corpus_size": (
            {"rho": round(float(r_auc.statistic), 4),
             "p": round(float(r_auc.pvalue), 4)} if len(pts) >= 5 else
            {"rho": round(float(r_auc.statistic), 4), "p": None,
             "p_withheld_because": f"{len(pts)} points; a p-value needs at least five"}
        ),
        "opposite_directions": bool(r_aa.statistic > 0 > r_auc.statistic),
        # The same question asked of section 5f's headline quantity. Reported whether or
        # not it agrees, because a trend that holds on one adjustment and not the other is
        # a property of the adjustment.
        "adjusted_vs_corpus_size": (
            {
                "rho": round(float(stats.spearmanr(
                    [p[0] for p in adj_pts], [p[1] for p in adj_pts]).statistic), 4),
                "n_points": len(adj_pts),
                "points": [{"n_agents": int(a), "adjusted": float(b)} for a, b in adj_pts],
            }
            if len(adj_pts) >= 3 else
            {"computed": False, "n_points": len(adj_pts),
             "reason": ("fewer than three converged fits have an adjusted figure; "
                        "`make across-agent` has to be run per corpus and the adjusted "
                        "series is therefore shorter than the unadjusted one")}
        ),
        # The note has to agree with what was actually reported. It said a p-value was
        # not worth quoting while the p-value sat two lines above it, because the
        # suppression threshold moved and the sentence did not.
        "note": (
            f"{len(pts)} converged fits on the expansion path carry this split."
            + ("" if len(pts) >= 5 else
               f" A rank correlation over {len(pts)} points carries no p-value; the sign "
               "is the claim.")
            + (" Five points is the fewest this script will attach a p-value to, and it "
               "is still five points." if len(pts) == 5 else "")
        ),
    }


def _prediction(rows: list[dict]) -> dict:
    """Written before the merged 65-agent LOAO landed, and scored clause by clause.

    The merged fit's leave-one-FAMILY-out across-agent figure is already on disk at
    +0.196 with a CI of [+0.020, +0.343], from the same posterior. So the prediction is
    not brave about the sign. What it is brave about is the magnitude: that the metric
    stays short of the +0.3 bar even at 65 agents and 9.10:1 identification, which is the
    difference between "the product's comparison works" and "the product's comparison is
    distinguishable from nothing".

    Three clauses, scored separately, because a prediction that can only be wholly right
    or wholly wrong hides which part of the reasoning failed.

    Grounds for the sign: leave-one-agent-out has been the more positive of the two splits
    at every corpus -- -0.015 against -0.167 on the registry, +0.047 against -0.139 on
    the absences-dropped fit -- so an already-positive family figure makes a negative
    agent figure unlikely. Grounds for the CI excluding zero: 65 folds contribute against
    the family split's 6. Grounds for falling short of +0.3: the three converged fits run
    -0.070, -0.015, +0.047, and an extrapolation of that series does not reach 0.3.
    """
    merged = next((r for r in rows if r["corpus"] == "merged 65"), None)
    doc = {
        "made": ("the merged 65-agent corpus will put leave-one-agent-out across-agent "
                 "Spearman above zero with a CI excluding zero, and still below +0.3"),
        "because": ("leave-one-agent-out has been the more positive split at every corpus; "
                    "the same posterior's family split is already +0.196 with a CI "
                    "excluding zero; 65 folds give a tighter interval than 6; and the "
                    "three converged fits run -0.070, -0.015, +0.047, which does not "
                    "extrapolate to +0.3"),
        "clauses": {"positive": None, "ci_excludes_zero": None, "below_declared_bar": None},
        "outcome": None,
    }
    if not merged or merged["status"] != "present":
        return doc
    aa = merged["splits"].get("leave_one_agent_out", {}).get("across_agent", {})
    if not aa.get("applicable"):
        return doc
    mean, ci = aa["model_mean"], aa["model_ci"]
    doc["clauses"] = {
        "positive": bool(mean > 0),
        "ci_excludes_zero": bool(ci[0] > 0 or ci[1] < 0),
        "below_declared_bar": bool(mean < SUPPORT_THRESHOLD),
    }
    doc["observed"] = {"model_mean": mean, "model_ci": ci,
                       "converged": merged["converged"]}
    hits = sum(1 for v in doc["clauses"].values() if v)
    doc["outcome"] = (
        "confirmed" if hits == 3 else
        "refuted" if hits == 0 else
        f"partly confirmed ({hits} of 3 clauses)"
    )
    if not merged["converged"]:
        doc["outcome"] += "; the fit did not converge, so the figures are not quotable"
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "across_agent_trend.json")
    args = ap.parse_args()
    _check_declaration()

    rows = [_read(*c) for c in CORPORA]
    _mark_off_chain(rows)
    present = [r for r in rows if r["status"] == "present"]
    pending = [r["corpus"] for r in rows if r["status"] == "pending"]

    print(f"{len(present)} of {len(rows)} corpora have a fit on disk."
          + (f" Pending: {', '.join(pending)}" if pending else ""))
    for split in SPLITS:
        carriers = [r for r in present if r["splits"].get(split, {})
                    .get("across_agent", {}).get("applicable")]
        if not carriers:
            continue
        print(f"\n{'=' * 78}\n{split}\n{'=' * 78}")
        print(f"  {'corpus':32s} {'ratio':>6s} {'dAUC':>8s} {'across':>8s} "
              f"{'adjusted':>9s}  verdict")
        for r in carriers:
            e = r["splits"][split]
            aa = e["across_agent"]
            flag = "" if r["converged"] else "  <- DID NOT CONVERGE"
            if not r.get("on_expansion_path"):
                flag += "  <- OFF THE EXPANSION PATH, excluded from the trend"
            # Only on the agent split. The adjusted figure is computed from
            # leave-one-agent-out fold predictions, so printing it under the family
            # split's table would label one split's number with another's -- the same
            # mistake this script already made once with the non-convergence flag.
            adj = r.get("adjusted") if split == "leave_one_agent_out" else None
            adj_txt = f"{adj['mean']:+9.4f}" if adj else f"{'--':>9s}"
            print(f"  {r['corpus']:32s} {r['identification_ratio']:6.2f} "
                  f"{e['delta_auc_mean']:+8.4f} {aa['model_mean']:+8.4f} "
                  f"{adj_txt}  {aa['verdict']}{flag}")

    trends = {split: _trend(rows, split) for split in SPLITS}
    for split, t in trends.items():
        if t.get("computed"):
            print(f"\n{split}: across-agent vs corpus size rho "
                  f"{t['across_agent_vs_corpus_size']['rho']:+.3f}, "
                  f"delta AUC vs corpus size rho "
                  f"{t['delta_auc_vs_corpus_size']['rho']:+.3f} -> "
                  f"{'OPPOSITE' if t['opposite_directions'] else 'same'} directions "
                  f"({t['n_points']} converged fits)")

    # Per split, not once. The first version of this kept a single slot and let the loop
    # overwrite it, so the flag ended up holding the family split's figure while the report
    # block printed it beside the agent split's table: a number labelled "the largest in
    # this table" that came from a different table. That is the defect section 9 opens with,
    # reproduced by the code written to describe it.
    nonconverged_best: dict[str, dict] = {}
    for split in SPLITS:
        carriers = [r for r in present if r["splits"].get(split, {})
                    .get("across_agent", {}).get("applicable")]
        if not carriers:
            continue
        best = max(carriers, key=lambda r: r["splits"][split]["across_agent"]["model_mean"])
        if not best["converged"]:
            nonconverged_best[split] = {
                "split": split, "corpus": best["corpus"],
                "model_mean": best["splits"][split]["across_agent"]["model_mean"],
                "worst_seed_gap": best["worst_seed_gap"],
            }
            print(f"\nWARNING: the strongest across-agent figure on {split} comes from "
                  f"{best['corpus']}, whose worst seed gap is {best['worst_seed_gap']} "
                  f"against a 0.3 threshold. It is not quotable.")

    prediction = _prediction(rows)
    if prediction["outcome"]:
        print(f"\nprediction: {prediction['outcome']}")
    else:
        print(f"\nprediction recorded, not yet scorable: {prediction['made']}")

    out = {
        "declaration": DECLARATION,
        "prediction": prediction,
        "support_threshold": SUPPORT_THRESHOLD,
        "corpora": rows,
        "pending": pending,
        "trends": trends,
        "strongest_figure_from_a_nonconverged_fit_by_split": nonconverged_best,
        "reading": (
            "The two discrimination metrics answer different questions and need not move "
            "together. Within-arm AUC ranks axes inside an arm, a task a design-blind "
            "constant scores about 0.84 on; across-agent Spearman ranks agents within an "
            "axis, which no constant can do. The product's question is the second one."
        ),
    }
    write_json(args.out, out, {})
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
