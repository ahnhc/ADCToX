"""A provenance stamp for every artefact.

Why this exists: not one artefact recorded what produced it -- no git revision, no raw
snapshot date, no input hashes -- while the plan's reproducibility section claims the
lineage is a hash chain. The cost of that gap is concrete and was paid repeatedly while
fixing this project: after changing the dataset builder mid-session, deciding whether a
running fit's output was still valid meant reasoning about which modules a process had
already imported. A stamp answers that from the file.

Deliberately small. It records what is cheap and unambiguous -- revision, whether the tree
was dirty, the pinned snapshot, the writing script, UTC time, and the sha256 of each named
input -- and claims nothing else. A `dirty` tree means the revision does not identify the
code, and that is worth knowing even though it cannot be fixed after the fact.

One thing an input hash is *not*: a staleness test. The digest of a directory covers every
file in it, and some of those files are themselves stamps carrying `written_utc`. So
regenerating a corpus deterministically -- same rows, same values -- still moves the hash,
because one of the hashed files records the time it was written. A hash difference therefore
means "something under here was rewritten", never "the data changed", and nothing in this
project decides anything on it. Establishing that a fit is still valid for the frames on
disk takes a comparison of the quantities the fit scored, not of this digest.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str | None:
    """Stripped stdout on success, or None if git could not answer.

    Empty output is a success and must not collapse to None. `git status --porcelain`
    prints nothing for a clean tree, so folding empty into None made `dirty` null exactly
    where it should read False -- for a clean checkout, the only state in which the recorded
    revision does identify the code. Null there is also indistinguishable from "git was
    unavailable", which is the opposite claim. A clean clone's test caught it; the working
    tree never could, because it was dirty whenever anything was being developed.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _sha256(path: Path, limit: int = 256 * 1024 * 1024) -> str | None:
    """Hash a file, or a directory's sorted file list and contents.

    Capped: a raw snapshot can be large, and a stamp that takes minutes gets removed.
    Over the cap the digest covers names and sizes only, and says so by its prefix.
    """
    try:
        if path.is_dir():
            h = hashlib.sha256()
            total = 0
            names = sorted(p for p in path.rglob("*") if p.is_file())
            for p in names:
                h.update(str(p.relative_to(path)).encode())
                h.update(str(p.stat().st_size).encode())
                total += p.stat().st_size
            if total <= limit:
                for p in names:
                    h.update(p.read_bytes())
                return f"sha256:{h.hexdigest()}"
            return f"names+sizes:{h.hexdigest()}"
        if path.stat().st_size > limit:
            return f"size:{path.stat().st_size}"
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def stamp(inputs: dict[str, str | Path] | None = None) -> dict:
    """The provenance block to embed under the key `provenance`."""
    rev = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return {
        "revision": rev or None,
        "dirty": bool(status) if status is not None else None,
        "snapshot": os.environ.get("ADCTOX_SNAPSHOT") or None,
        "script": Path(sys.argv[0]).name if sys.argv and sys.argv[0] else None,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            name: _sha256(Path(p)) for name, p in sorted((inputs or {}).items())
        },
    }


def write_json(path: Path, doc: dict, inputs: dict[str, str | Path] | None = None) -> None:
    """Write an artefact with its provenance attached.

    The stamp goes in rather than beside, because a sidecar gets separated from the file it
    describes the first time someone copies one of them.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**doc, "provenance": stamp(inputs)}
    path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
