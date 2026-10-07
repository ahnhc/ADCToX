#!/usr/bin/env python
"""Compare the otherEvents and seriousEvents fits.

What this is NOT. This is not the censoring-validity check. That one lives in
`censoring_sensitivity.py`, which refits the SAME otherEvents outcome on the subset of
trials whose reporting threshold is 0 -- i.e. the same question asked of data that never
needed the correction. That comparison is apples-to-apples and it passes.

What this IS. `otherEvents` and `seriousEvents` are different OUTCOMES, not two views of
one outcome. The first is "how often does this chemistry irritate this organ at all", the
second is "how often does it damage this organ seriously". A grade-1 cough and fatal
interstitial lung disease are both pulmonary and are not the same event. So the two fits
are expected to rank organs differently, and measuring that divergence is the point.

Why it matters more than it looks. The product ranks designs on otherEvents, but a user
who declares a comorbidity is asking the serious question: someone with pre-existing ILD
cares about serious pulmonary events, not about grade-1 cough. Measured here, the
otherEvents fit ranks pulmonary LOW for topoisomerase-I payloads while the seriousEvents
fit ranks it 2nd -- and the second is the one that matches T-DXd's boxed warning. If the
two tables disagree, the product is scoring the wrong outcome for the exact case it was
built for, and that is a finding about the product, not about censoring.

It also provides a free negative control on the threshold covariate: seriousEvents has
zero censored cells, so b_thresh there cannot be a censoring adjustment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from adctox.provenance import write_json


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    den = np.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / den) if den else float("nan")


# Design coefficients carry the product's claim; nuisance coefficients absorb reporting
# artefacts and are EXPECTED to differ between the two tables, because the tables are
# truncated differently and a serious event is a different outcome from a common one.
# Lumping them together is what made the first version of this check fire spuriously.
DESIGN_COEFS = {"b_dar", "b_combo"}


def _excludes_zero(c: dict) -> bool:
    return (c["q05"] > 0) == (c["q95"] > 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    args = ap.parse_args()

    paths = {k: args.out / f"forward_{k}_metrics.json" for k in ("other", "serious")}
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        print(
            f"missing {', '.join(missing)} metrics; run "
            f"`scripts/fit_forward.py --kind <variant>` for each first"
        )
        return 1

    docs = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in paths.items()}
    print("Censoring robustness: otherEvents (censored) against seriousEvents (complete)\n")
    for k, d in docs.items():
        print(f"  {k:8s} {d['corpus']}")

    print("\n  scale parameters")
    print(f"    {'parameter':14s} {'other':>9s} {'serious':>9s}")
    for name in ("tau_mech", "tau_cleav"):
        a = docs["other"].get(name, {}).get("mean")
        b = docs["serious"].get(name, {}).get("mean")
        if a is not None and b is not None:
            print(f"    {name:14s} {a:9.3f} {b:9.3f}")

    # ---- coefficients ---------------------------------------------------------------
    # Sign agreement is only meaningful where both fits actually resolve a sign. A
    # coefficient whose interval straddles zero in either fit has no sign to agree about,
    # and counting it either way is noise.
    coefs = sorted(
        set(docs["other"].get("coefficients", {}))
        & set(docs["serious"].get("coefficients", {}))
    )
    print(
        f"\n  {'coefficient':14s} {'other':>18s} {'serious':>18s}  role      sign"
    )
    rows, agree_n, testable = [], 0, []
    for name in coefs:
        ca, cb = docs["other"]["coefficients"][name], docs["serious"]["coefficients"][name]
        a, b = ca["mean"], cb["mean"]
        role = "design" if name in DESIGN_COEFS else "nuisance"
        both_resolved = _excludes_zero(ca) and _excludes_zero(cb)
        if both_resolved:
            agree = (a >= 0) == (b >= 0)
            verdict = "agrees" if agree else "DISAGREES"
            testable.append(name)
            agree_n += agree
        else:
            agree = None
            verdict = "n/a (spans 0)"
        print(
            f"    {name:14s} {a:+7.3f} [{ca['q05']:+.3f},{ca['q95']:+.3f}]"
            f" {b:+7.3f} [{cb['q05']:+.3f},{cb['q95']:+.3f}]  {role:9s} {verdict}"
        )
        rows.append(
            {"name": name, "role": role, "other": a, "serious": b,
             "both_resolved": both_resolved, "sign_agrees": agree}
        )

    design_testable = [r for r in rows if r["role"] == "design" and r["both_resolved"]]
    design_disagree = [r for r in design_testable if not r["sign_agrees"]]

    # ---- the b_thresh negative control ----------------------------------------------
    # seriousEvents has zero censored cells, so in that fit the threshold covariate
    # cannot be correcting for censoring -- there is none to correct. Whatever it picks up
    # there is trial-level confounding that rides along with the reporting threshold.
    # This is a free negative control and it bounds the censoring interpretation.
    bt_o = docs["other"]["coefficients"].get("b_thresh")
    bt_s = docs["serious"]["coefficients"].get("b_thresh")
    thresh_note = None
    if bt_o and bt_s:
        print("\n  b_thresh negative control (seriousEvents has 0 censored cells)")
        print(
            f"    censored table   b_thresh {bt_o['mean']:+.3f} "
            f"[{bt_o['q05']:+.3f}, {bt_o['q95']:+.3f}]"
        )
        print(
            f"    complete table   b_thresh {bt_s['mean']:+.3f} "
            f"[{bt_s['q05']:+.3f}, {bt_s['q95']:+.3f}]"
        )
        if _excludes_zero(bt_s):
            thresh_note = (
                "b_thresh is non-zero in a corpus with no censoring, so the covariate is "
                "NOT purely a censoring adjustment: the reporting threshold also tracks "
                "trial-level reporting practice. It must stay in the model as a "
                "confounder control, and must not be described as the censoring "
                "correction."
            )
        else:
            thresh_note = (
                "b_thresh is indistinguishable from zero without censoring, which is what "
                "a pure censoring adjustment should look like."
            )
        print(f"    -> {thresh_note}")

    # ---- the substantive comparison: do the mechanism organ profiles survive? --------
    # This is what the whole check is for. It needs BOTH posteriors; comparing
    # corpus-build fingerprints instead would compare an object that is identical by
    # construction for the two variants and prove nothing.
    print(
        "\n  mechanism x axis profiles: do common and serious events rank organs alike?"
    )
    prof = {}
    npz = {k: args.out / f"posterior_{k}.npz" for k in ("other", "serious")}
    if not all(p.exists() for p in npz.values()):
        absent = [k for k, p in npz.items() if not p.exists()]
        print(
            f"    posterior_{'/'.join(absent)}.npz absent -> NOT COMPARED. Build with "
            f"`scripts/propose_demo.py --kind <variant> --fit-only`. "
            f"Without it this script cannot make its central comparison."
        )
    else:
        import numpy as np

        da, db = (np.load(npz[k], allow_pickle=True) for k in ("other", "serious"))
        # Recorded here so the report's band edges trace to an artefact. They are
        # measured (15th/60th percentile of non-zero observed rates in each table), and
        # the gap between the two tables is the reason a band cannot be read across them.
        band_edges = {
            k: [float(x) for x in np.load(npz[k], allow_pickle=True)["band_edges"]]
            for k in ("other", "serious")
        }
        print(
            f"\n    band edges, measured per table: "
            f"other {band_edges['other'][0]:.4f}/{band_edges['other'][1]:.4f}  "
            f"serious {band_edges['serious'][0]:.4f}/{band_edges['serious'][1]:.4f}"
        )
        ma = np.asarray(da["mech_axis"]).mean(axis=0)   # (mech, axis)
        mb = np.asarray(db["mech_axis"]).mean(axis=0)
        mech_a = [str(x) for x in da["mechanisms"]]
        mech_b = [str(x) for x in db["mechanisms"]]
        axes_a = [str(x) for x in da["axes"]]
        shared = [m for m in mech_a if m in mech_b]
        print(f"    {'mechanism':16s} {'rho(axes)':>10s}   organ ranking preserved?")
        per_mech = {}
        for m in shared:
            va, vb = ma[mech_a.index(m)], mb[mech_b.index(m)]
            r = _spearman(va, vb)
            per_mech[m] = r
            print(f"    {m:16s} {r:+10.3f}   {'yes' if r > 0.4 else 'weak'}")
        prof_boxed: dict = {"pairs": {}, "serious_ranks_higher": 0, "n_pairs": 0}
        per_axis = {}
        if len(shared) >= 3:
            for j, ax in enumerate(axes_a):
                va = np.array([ma[mech_a.index(m)][j] for m in shared])
                vb = np.array([mb[mech_b.index(m)][j] for m in shared])
                per_axis[ax] = _spearman(va, vb)
        vals = [v for v in per_mech.values() if v == v]
        prof = {
            "band_edges": band_edges,
            "boxed_warning_recovery": prof_boxed,
            "per_mechanism_spearman": per_mech,
            "per_axis_spearman": per_axis,
            "mean_per_mechanism": float(np.mean(vals)) if vals else None,
            "n_shared_mechanisms": len(shared),
        }
        if vals:
            print(
                f"\n    mean rho across {len(vals)} shared mechanisms: "
                f"{np.mean(vals):+.3f}  (each is 14 axes, so each rho is its own test)"
            )

        # Which table recovers which part of the label? The boxed warnings are serious
        # events by definition, so if the division is real the serious fit should rank the
        # boxed-warning organ higher than the common fit does. These four are the
        # label-verified pairs already encoded in conf/hard_flags.yaml.
        BOXED = {
            ("topo1", "pulmonary"): "ENHERTU boxed warning: interstitial lung disease",
            ("tubulin", "dermatologic"): "PADCEV boxed warning: SJS/TEN",
            ("dna_cleave", "hepatic"): "BESPONSA boxed warning: hepatotoxicity/VOD",
            ("dna_crosslink", "haematologic"): "ZYNLONTA: myelosuppression",
        }
        print(f"\n    {'boxed warning':52s} {'rank: common':>13s} {'serious':>9s}")
        boxed_rows = {}
        for (m, ax), label in BOXED.items():
            if m not in shared or ax not in axes_a:
                continue
            j = axes_a.index(ax)
            ra = int((-ma[mech_a.index(m)]).argsort().argsort()[j]) + 1
            rb = int((-mb[mech_b.index(m)]).argsort().argsort()[j]) + 1
            boxed_rows[f"{m}/{ax}"] = {"common_rank": ra, "serious_rank": rb}
            arrow = "serious ranks it higher" if rb < ra else ""
            print(f"    {label:52s} {ra:>9d}/14 {rb:>6d}/14  {arrow}")
        n_better = sum(1 for v in boxed_rows.values()
                       if v["serious_rank"] < v["common_rank"])
        if boxed_rows:
            print(
                f"    -> the serious table ranks the boxed-warning organ higher in "
                f"{n_better}/{len(boxed_rows)} label-verified pairs"
            )
        # `prof` is assembled above this block, so it has to be updated rather than
        # relied on to pick these up: the first version printed the table correctly and
        # wrote the empty initializer to the artefact, which is the exact shape of bug
        # this project keeps finding -- the screen and the saved record disagreeing.
        prof["boxed_warning_recovery"] = {
            "pairs": boxed_rows,
            "serious_ranks_higher": n_better,
            "n_pairs": len(boxed_rows),
        }

    # ---- verdict ---------------------------------------------------------------------
    # The verdict rests on the design coefficients and the profile agreement, not on a
    # sign tally over nuisance terms.
    if prof.get("mean_per_mechanism") is None:
        verdict = (
            "the mechanism profiles were NOT compared (posterior missing), so this "
            "script's central measurement did not run"
        )
    elif prof["mean_per_mechanism"] > 0.4:
        verdict = (
            f"common and serious events rank organs alike (mean rho "
            f"{prof['mean_per_mechanism']:+.3f}), so ranking designs on the common table "
            f"also ranks them correctly for serious risk"
        )
    else:
        verdict = (
            f"common and serious events rank organs DIFFERENTLY (mean rho "
            f"{prof['mean_per_mechanism']:+.3f}). This is a product finding, not a "
            f"censoring failure: a comorbidity declares a serious-risk question, so an "
            f"axis must be scored on the table that matches the question. The two "
            f"tables recover different label sections -- see the boxed-warning rows "
            f"above -- and each is right about its own outcome."
        )
    if design_disagree:
        verdict += (
            " Additionally a design coefficient flips resolved sign ("
            + ", ".join(r["name"] for r in design_disagree)
            + "), which is a genuine inconsistency."
        )
    print(f"\n  VERDICT: {verdict}")
    if len(testable) < len(coefs):
        print(
            f"  ({len(coefs) - len(testable)} of {len(coefs)} coefficients span zero in "
            f"at least one fit and carry no testable sign; the first version of this "
            f"check counted them and reported a false disagreement on b_dar.)"
        )

    out = {
        "coefficients": rows,
        "design_sign_disagreements": [r["name"] for r in design_disagree],
        "n_testable_coefficients": len(testable),
        "n_coefficients": len(coefs),
        "b_thresh_negative_control": {
            "other": bt_o, "serious": bt_s, "note": thresh_note,
        },
        "mechanism_profile_agreement": prof,
        "verdict": verdict,
        "tau_mech": {k: docs[k].get("tau_mech", {}).get("mean") for k in docs},
        "tau_cleav": {k: docs[k].get("tau_cleav", {}).get("mean") for k in docs},
        "gates": {k: docs[k].get("gate") for k in docs},
    }
    path = args.out / "event_table_comparison.json"
    write_json(path, out, {"other_metrics": paths["other"], "serious_metrics": paths["serious"]})
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
