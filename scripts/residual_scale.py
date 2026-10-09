"""How much of the between-agent variation do the seven design slots actually account for?

`sigma_agent` is the residual between-agent scale left after the design slots have had their
say; `tau_mech` is the scale of the mechanism x axis interaction the slots supply. Neither
number means much alone -- both are standard deviations in logit space -- but their ratio is
the quantity the report makes a claim about, and until now that claim was a hand-written
string in the report generator rather than a measurement.

It had gone stale. The sentence beside `sigma_agent` read "small, so the design slots
account for much of the between-agent variation", written when the parameter stood at 0.159
on the 16-agent registry corpus. The corpus rebuild moved it to 0.343 and the sentence did
not move, because `check_report.py` pins every decimal figure to an artefact and has no
power at all over the prose next to it.

So the ratio becomes a measured value with its own artefact, on both tables. The
seriousEvents table matters here beyond robustness: it has no censored cells, so the
residual cannot be an artefact of the censoring model, and it is the table on which the
original claim does not merely weaken but reverses.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adctox.provenance import write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Above this, the residual between-agent scale is at least as large as the mechanism effect,
# and the design slots cannot be said to account for the between-agent variation. The band is
# a reading of the ratio, not a test: there is no null here, only two scales to compare.
ACCOUNTS_FOR = 0.40
DOES_NOT_ACCOUNT_FOR = 0.90


def _ratio(metrics: dict) -> dict | None:
    sa = metrics.get("coefficients", {}).get("sigma_agent")
    tm = metrics.get("tau_mech")
    if not sa or not tm or not tm.get("mean"):
        return None
    ratio = sa["mean"] / tm["mean"]
    if ratio < ACCOUNTS_FOR:
        reading = "design slots account for much of the between-agent variation"
    elif ratio < DOES_NOT_ACCOUNT_FOR:
        reading = "comparable scales: the slots account for part of it"
    else:
        reading = "the residual exceeds the mechanism effect: the slots do not account for it"
    return {
        "sigma_agent": sa,
        "tau_mech": tm,
        "ratio": ratio,
        # The interval is carried through as a ratio too, so a reader can see that the
        # comparison is not resting on two point estimates.
        "ratio_q05": sa["q05"] / tm["mean"],
        "ratio_q95": sa["q95"] / tm["mean"],
        "reading": reading,
        # Carried verbatim rather than parsed: the corpus line is a human-readable string in
        # the fit's own artefact, and a regex over it would be a second place to get wrong.
        "corpus": metrics.get("corpus"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts", type=pathlib.Path, default=ROOT / "artifacts")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "residual_scale.json")
    args = ap.parse_args()

    tables = {}
    for kind in ("other", "serious"):
        path = args.artifacts / f"forward_{kind}_metrics.json"
        if not path.exists():
            continue
        got = _ratio(json.loads(path.read_text(encoding="utf-8")))
        if got:
            tables[kind] = got

    if not tables:
        print("no fitted metrics to read", file=sys.stderr)
        return 1

    # Every scale the report phrases against `tau_mech` is recorded here, not only the
    # residual. "about half the size of the mechanism scale" sat beside `tau_cleav` as a
    # hand-written fraction for the same reason the sigma_agent sentence did, and a figure
    # the report prints has to be pinned to an artefact to be checkable at all.
    against_mech = {}
    for kind in ("other", "serious"):
        path = args.artifacts / f"forward_{kind}_metrics.json"
        if not path.exists():
            continue
        m = json.loads(path.read_text(encoding="utf-8"))
        tm = m.get("tau_mech", {}).get("mean")
        if not tm:
            continue
        row = {}
        for name in ("tau_cleav", "tau_family"):
            cell = m.get(name)
            if isinstance(cell, dict) and cell.get("mean"):
                row[name] = cell["mean"] / tm
        for name in ("sigma_agent", "sigma_trial"):
            cell = m.get("coefficients", {}).get(name)
            if isinstance(cell, dict) and cell.get("mean"):
                row[name] = cell["mean"] / tm
        against_mech[kind] = row

    # Ratios between the two event tables. The report's argument that `b_thresh` is a
    # reporting covariate rather than the censoring correction is precisely that it is
    # larger on the table with no censored cells, and that multiple was a hand-written
    # "four times" until it was measured at 3.7318.
    across = {}
    if len(tables) == 2:
        mo = json.loads((args.artifacts / "forward_other_metrics.json")
                        .read_text(encoding="utf-8"))
        msv = json.loads((args.artifacts / "forward_serious_metrics.json")
                         .read_text(encoding="utf-8"))
        for name in ("b_thresh", "b_log_n", "b_combo", "b_dar"):
            a = mo.get("coefficients", {}).get(name, {}).get("mean")
            b = msv.get("coefficients", {}).get(name, {}).get("mean")
            if a and b:
                across[name] = {
                    "other": a,
                    "serious": b,
                    "serious_over_other": b / a,
                    # Recorded separately: a sign flip is a different finding from a
                    # magnitude change, and a ratio alone hides it.
                    "same_sign": (a > 0) == (b > 0),
                }

    doc = {
        "bands": {"accounts_for": ACCOUNTS_FOR, "does_not_account_for": DOES_NOT_ACCOUNT_FOR},
        "tables": tables,
        "against_tau_mech": against_mech,
        "across_tables": across,
        # The two tables disagreeing about which side of 1.0 the ratio sits on is the finding,
        # so it is recorded rather than left for a reader to notice.
        "reverses_across_tables": (
            len(tables) == 2
            and (tables["other"]["ratio"] < 1.0) != (tables["serious"]["ratio"] < 1.0)
        ),
    }
    write_json(args.out, doc)
    for kind, t in tables.items():
        print(f"{kind:8} sigma_agent {t['sigma_agent']['mean']:.4f} / tau_mech "
              f"{t['tau_mech']['mean']:.4f} = {t['ratio']:.4f}  -- {t['reading']}")
    if doc["reverses_across_tables"]:
        print("the reading reverses between the two tables")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
