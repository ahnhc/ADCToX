"""The guard that stops one corpus's predictions being adjusted with another's conditions.

This exists because the mistake happened and nearly got reported as a result. The
across-agent analysis correlates two series that both come from the fold-prediction
artefact, while `--processed` supplies only the per-agent nuisance conditions used for the
adjustment. Running it against the literature-augmented corpus while the fold predictions
were still the registry-only ones moved the headline from +0.1332 (p = 0.0250) to +0.2118
(p = 0.0010) -- entirely because the paper arms are all monotherapy by construction, which
changed every agent's combination fraction and so changed b_combo from 0.0482 to 0.5369.

The giveaway was that the *unadjusted* mean came out identical to four decimal places,
which adding 312 arms and 1,413 observations cannot do. Nothing in the pipeline would have
said so.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "across_agent_adjusted.py"
FOLD_PREDICTIONS = ROOT / "artifacts" / "forward_other_fold_predictions.parquet"
METRICS = ROOT / "artifacts" / "forward_other_metrics.json"
UNION = ROOT / "data" / "processed" / "with_literature"


def _run(processed: pathlib.Path, out: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--processed", str(processed), "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT,
    )


@pytest.mark.skipif(not FOLD_PREDICTIONS.exists(), reason="run `make forward` first")
def test_a_corpus_the_predictions_did_not_come_from_is_refused(tmp_path) -> None:
    if not UNION.exists():
        pytest.skip("run `make pmc-merge` with --union first")
    r = _run(UNION, tmp_path)
    assert r.returncode == 1, r.stdout[-2000:]
    assert "corpus mismatch" in r.stderr
    # Both reasons have to be named, because the agent-set check alone misses the
    # dangerous case: the same agents with more arms.
    assert "agents differ" in r.stderr
    assert "the fitted corpus differs" in r.stderr


@pytest.mark.skipif(not FOLD_PREDICTIONS.exists(), reason="run `make forward` first")
def test_the_corpus_the_predictions_came_from_still_passes(tmp_path) -> None:
    """The guard must not block the analysis it is protecting."""
    r = _run(ROOT / "data" / "processed", tmp_path)
    assert r.returncode == 0, r.stderr[-2000:]
    written = json.loads((tmp_path / "across_agent_adjusted.json").read_text())
    assert written["variants"]


@pytest.mark.skipif(not METRICS.exists(), reason="run `make forward` first")
def test_the_fitted_corpus_summary_is_recorded_for_the_guard_to_use() -> None:
    """The agent-set check cannot see a changed arm count, so the guard depends on
    `fit_forward.py` recording the corpus it fitted. If that key ever disappears the guard
    silently weakens to the agent-set check alone."""
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    assert metrics["corpus"]
    assert "arms" in metrics["corpus"] and "agents" in metrics["corpus"]
