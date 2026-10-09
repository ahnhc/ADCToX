"""A script that writes a corpus is the one that can break a running fit.

This project lost a twenty-minute fit to exactly that: the denominator fallback rewrote
`data/processed/with_atlas/` while a fit was reading it, and the plan's own hard gate is
freeze-then-fit. The guard is in `restrict_corpus_agents.py` because that is the script
whose output a fit reads directly.

Two properties, and the first is what makes the second possible: an unconditional rewrite
of identical bytes is harmless and an unconditional rewrite of different bytes is the
failure, and from the outside the two are indistinguishable. So the frames are staged and
compared, and only a real change is subject to the reader check.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import restrict_corpus_agents as rca  # noqa: E402


def test_identical_frames_are_not_rewritten(tmp_path: pathlib.Path) -> None:
    frame = pd.DataFrame({"agent": ["a", "b"], "n": [1, 2]})
    out = tmp_path / "corpus"
    out.mkdir()
    assert rca._publish({"arms.parquet": frame}, out) is True
    first = rca._sha(out / "arms.parquet")
    mtime = (out / "arms.parquet").stat().st_mtime_ns
    assert rca._publish({"arms.parquet": frame}, out) is True
    assert rca._sha(out / "arms.parquet") == first
    assert (out / "arms.parquet").stat().st_mtime_ns == mtime, (
        "the file was rewritten although the bytes are identical; a fit reading it would "
        "see a changed mtime and the guard would have nothing to fire on"
    )


def test_a_real_change_is_written(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "corpus"
    out.mkdir()
    rca._publish({"arms.parquet": pd.DataFrame({"agent": ["a"]})}, out)
    before = rca._sha(out / "arms.parquet")
    rca._publish({"arms.parquet": pd.DataFrame({"agent": ["a", "b"]})}, out)
    assert rca._sha(out / "arms.parquet") != before


def test_a_change_is_refused_while_a_fit_reads_the_directory(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    out = tmp_path / "with_literature_26agents"
    out.mkdir()
    rca._publish({"arms.parquet": pd.DataFrame({"agent": ["a"]})}, out)
    before = rca._sha(out / "arms.parquet")
    monkeypatch.setattr(
        rca, "_reader_running",
        lambda o: "4242 python scripts/fit_forward.py --processed "
                  "data/processed/with_literature_26agents",
    )
    assert rca._publish({"arms.parquet": pd.DataFrame({"agent": ["a", "b"]})}, out) is False
    assert rca._sha(out / "arms.parquet") == before, "the frames changed despite the refusal"


def test_the_reader_check_does_not_fire_on_an_unrelated_fit(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """A fit on another corpus must not block this one."""
    out = tmp_path / "with_literature_26agents"
    out.mkdir()
    other = tmp_path / "with_atlas"
    other.mkdir()
    monkeypatch.setattr(rca, "_argv_of", lambda pid: [
        "/usr/bin/python", "scripts/fit_forward.py", "--processed", str(other),
    ])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, "999\n", "",
    ))
    assert rca._reader_running(out) is None


def test_the_reader_check_does_not_fire_on_a_word_in_a_shell_wrapper(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """The false positive that this guard produced on its first run.

    Matching the output directory's name as a substring of a `pgrep -af` line hit the shell
    wrappers of earlier commands, whose quoted text contains the word. A test writing to a
    directory called `corpus` was told a fit was reading it and the write was refused. A
    guard that fires on a word in an unrelated command line stops real work.
    """
    out = tmp_path / "corpus"
    out.mkdir()
    monkeypatch.setattr(rca, "_argv_of", lambda pid: [
        "/bin/bash", "-c",
        "cat > fit.sh <<SH\npython scripts/fit_forward.py --processed corpus\nSH",
    ])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, "999\n", "",
    ))
    assert rca._reader_running(out) is None


def test_the_reader_check_fires_on_a_real_fit(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    out = tmp_path / "with_literature_26agents"
    out.mkdir()
    monkeypatch.setattr(rca, "_argv_of", lambda pid: [
        "/home/x/.venv/bin/python", "scripts/fit_forward.py", "--processed", str(out),
        "--out", "artifacts/x",
    ])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, "4242\n", "",
    ))
    found = rca._reader_running(out)
    assert found and "fit_forward.py" in found


def test_the_script_measures_whether_it_held_the_agent_set_fixed() -> None:
    """Its purpose is to vary the arms and not the agents, and it does not fully manage it.

    Restoring an agent's upper-bound arms can promote that agent into the model grid, so an
    arm restriction is also a grid restriction. The artefact records which agents moved,
    because the alternative is noticing it in a fit's first line -- which is how it was
    noticed, after the fit had started.
    """
    import json

    path = ROOT / "artifacts" / "restricted_corpus.json"
    if not path.exists():
        return
    doc = json.loads(path.read_text(encoding="utf-8"))
    for key in ("grid_agents_reference", "grid_agents_written",
                "grid_agents_promoted_by_keeping_bounded_arms", "grid_agents_lost",
                "holds_the_agent_set_fixed"):
        assert key in doc, f"{key} is not recorded; the restriction is unverified"
    moved = (doc["grid_agents_promoted_by_keeping_bounded_arms"]
             + doc["grid_agents_lost"])
    assert doc["holds_the_agent_set_fixed"] == (not moved)
    if moved:
        assert doc["why_not"], "agents moved and no reason is recorded"
        assert (doc["grid_agents_written"] - doc["grid_agents_reference"]
                == len(doc["grid_agents_promoted_by_keeping_bounded_arms"])
                - len(doc["grid_agents_lost"]))
