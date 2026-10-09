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

It does not fully succeed, and the script now measures its own failure rather than leaving
it to be noticed in a fit's first line. The restriction is applied to the arm table, and
whether an agent reaches the model *grid* depends on the cells its arms carry, so keeping an
agent's upper-bound arms can promote it into the grid when dropping them kept it out.
Praluzatamab ravtansine does exactly that: 26 grid agents in the reference corpus, 27 here.
The arm set and the grid are not independent, so "the same agents with different arms" is
not a corpus that exists here -- what this writes takes the confound from six agents to one.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.model import dataset as ds
from adctox.provenance import write_json
from adctox.taxonomy import default_taxonomy

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _argv_of(pid: str) -> list[str]:
    """A process's argv as a list, or empty. Separate so a test can stand in for it."""
    try:
        raw = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().decode()
    except (OSError, UnicodeDecodeError):
        return []
    return [a for a in raw.split("\0") if a]


def _reader_running(out: pathlib.Path) -> str | None:
    """Is a fit reading this corpus right now?

    This project has already lost a twenty-minute fit to a corpus that was rewritten while
    the fit was reading it, and the plan's own hard gate is freeze-then-fit. A script whose
    job is to write a corpus is the one that can break it, so it checks.

    The check reads argv from /proc rather than matching text in a `pgrep -af` line, and
    the reason is a false positive it produced immediately. Matching the output directory's
    *name* as a substring hit the shell wrappers of earlier commands, whose text happens to
    contain the word -- so a test writing to a directory called `corpus` was told a fit was
    reading it, and the write was refused. A guard that fires on a word in an unrelated
    command line is a guard that stops real work.

    So a reader is: a process whose argv names `fit_forward.py` as a script and carries
    `--processed <path>` resolving to this directory. A shell wrapper quoting that same
    command line has `bash` as argv[0] and the whole script as one argument, so it does not
    match either test.
    """
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "fit_forward.py"], capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    target = out.resolve()
    for pid in proc.stdout.split():
        argv = _argv_of(pid)
        if not argv or not any(a.endswith("fit_forward.py") for a in argv):
            continue
        if "--processed" not in argv:
            continue
        where = argv[argv.index("--processed") + 1:argv.index("--processed") + 2]
        if not where:
            continue
        try:
            if pathlib.Path(where[0]).resolve() == target:
                return f"{pid} {' '.join(argv)}"
        except OSError:
            continue
    return None


def _publish(frames: dict, out: pathlib.Path) -> bool:
    """Write the frames only if they differ, and never while a fit is reading them.

    An unconditional rewrite of identical bytes is harmless and an unconditional rewrite of
    different bytes is the failure above, and from the outside the two look the same. So the
    bytes are produced in a temporary directory first and compared.
    """
    with tempfile.TemporaryDirectory() as tmp:
        staged = pathlib.Path(tmp)
        for name, frame in frames.items():
            frame.to_parquet(staged / name, index=False)
        changed = [
            name for name in frames
            if not (out / name).exists() or _sha(out / name) != _sha(staged / name)
        ]
        if not changed:
            print(f"{out}/ is already exactly these frames; nothing written")
            return True
        reader = _reader_running(out)
        if reader:
            print(
                f"refusing to rewrite {out}/ -- it would change "
                f"{', '.join(changed)} and a fit is reading it:\n  {reader}\n"
                "Wait for the fit, or write to a different --out. A corpus that changes "
                "under a running fit makes that fit unattributable to any corpus.",
                file=sys.stderr,
            )
            return False
        for name in changed:
            shutil.copy2(staged / name, out / name)
        print(f"wrote {', '.join(changed)} to {out}/")
    return True


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
    if not _publish({"arms.parquet": out_arms, "observations.parquet": out_obs}, args.out):
        return 1

    dropped = sorted(set(arms.agent.dropna()) - keep)

    # The arm table's agent column is not the model's agent grid. The restriction is
    # applied to the former and the comparison is made on the latter, so the thing this
    # script exists to hold fixed has to be checked on the grid or it is not checked at
    # all. Reported, not enforced: the mismatch is a property of the corpora and the fit
    # is still worth having.
    axes = list(default_taxonomy().axis_order)
    grid_ref = set(ds.load(args.agents_from, axes, kind="other").agents)
    grid_out = set(ds.load(args.out, axes, kind="other").agents)
    promoted = sorted(grid_out - grid_ref)
    demoted = sorted(grid_ref - grid_out)
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
        "grid_agents_reference": len(grid_ref),
        "grid_agents_written": len(grid_out),
        "grid_agents_promoted_by_keeping_bounded_arms": promoted,
        "grid_agents_lost": demoted,
        "holds_the_agent_set_fixed": not promoted and not demoted,
        "why_not": (
            None if not (promoted or demoted) else
            "an agent reaches the model grid on the cells its arms carry, so restoring an "
            "agent's upper-bound arms can promote it into the grid; the restriction is "
            "applied to the arm table and the comparison is made on the grid"
        ),
        "purpose": ("the missing cell of the 2x2: the agents of the explicit-cuts corpus "
                    "with all of their arms, so the arm set and the agent set stop moving "
                    "together -- which it achieves to within the agents named above"),
    }
    write_json(args.report, report)
    print(f"arms {report['arms_in']} -> {report['arms_out']}, "
          f"agents {report['agents_in']} -> {report['agents_out']}")
    print(f"dropped: {dropped}")
    print(f"upper-bound arms kept: {report['upper_bound_arms_kept']}")
    print(f"grid agents: reference {len(grid_ref)} -> written {len(grid_out)}")
    if promoted or demoted:
        print(f"  the agent set is NOT held fixed: promoted {promoted}, lost {demoted}")
        print("  an arm restriction is also a grid restriction; see the artefact's why_not")
    else:
        print("  the agent set is held fixed")
    print(f"-> {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
