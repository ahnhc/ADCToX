"""Restrict a corpus to another corpus's agents, keeping every arm those agents have.

Why this exists: two chain steps were supposed to isolate the censoring treatment and do
not. Step 3 drops uninformative absences from the 32-agent corpus and scores -0.1564 on
leave-one-mechanism-out; step 4 keeps only the tables that stated a cut, lands on 26 agents
and scores -0.014, which is the registry corpus's number. Both leave 663 censored cells, so
the censoring state is held fixed -- and the agent set is not. Step 4 loses six agents,
every one of them an agent whose only literature arms are upper-bound, so the pair changes
the arms and the agents together and attributes the difference to whichever the reader had
in mind.

This writes the missing cell of the 2x2: the same 26 agents with **all** of their arms,
upper-bound ones included. If that fit is bad, the damage is in the arms. If it is good, the
damage is in the six agents, and "the bounded threshold" was never the explanation.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_literature_final",
                    help="corpus whose arms are kept")
    ap.add_argument("--agents-from", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_explicit_threshold",
                    help="corpus whose agent list defines the restriction")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "with_literature_26agents")
    ap.add_argument("--report", type=pathlib.Path,
                    default=ROOT / "artifacts" / "restricted_corpus.json")
    args = ap.parse_args()

    arms = pd.read_parquet(args.source / "arms.parquet")
    obs = pd.read_parquet(args.source / "observations.parquet")
    keep = set(
        pd.read_parquet(args.agents_from / "arms.parquet")["agent"].dropna().unique()
    )

    out_arms = arms[arms.agent.isin(keep) | arms.agent.isna()]
    out_obs = obs[obs.agent.isin(keep)]
    args.out.mkdir(parents=True, exist_ok=True)
    out_arms.to_parquet(args.out / "arms.parquet", index=False)
    out_obs.to_parquet(args.out / "observations.parquet", index=False)

    dropped = sorted(set(arms.agent.dropna()) - keep)
    ub = out_arms.threshold_is_upper_bound.fillna(True).astype(bool) \
        if "threshold_is_upper_bound" in out_arms.columns else None
    report = {
        "source": str(args.source.relative_to(ROOT)),
        "agents_from": str(args.agents_from.relative_to(ROOT)),
        "arms_in": int(len(arms)),
        "arms_out": int(len(out_arms)),
        "agents_in": int(arms.agent.nunique()),
        "agents_out": int(out_arms.agent.nunique()),
        "agents_dropped": dropped,
        "upper_bound_arms_kept": int(ub.sum()) if ub is not None else None,
        "purpose": ("the missing cell of the 2x2: the agents of the explicit-cuts corpus "
                    "with all of their arms, so the arm set and the agent set stop moving "
                    "together"),
    }
    write_json(args.report, report)
    print(f"arms {report['arms_in']} -> {report['arms_out']}, "
          f"agents {report['agents_in']} -> {report['agents_out']}")
    print(f"dropped: {dropped}")
    print(f"upper-bound arms kept: {report['upper_bound_arms_kept']}")
    print(f"-> {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
