"""The trend table reverses a reading, so its guards matter more than its numbers.

Three things can go wrong in a way that would make the table say the opposite of the
truth, and each has happened in this project in some other form:

1. The pre-declared threshold drifts. The +0.3 bar was declared in `fit_forward.py`
   before the metric was first computed. If that sentence is edited away and the bar is
   left behind as a bare constant here, the script scores against a threshold nothing
   declared -- which is how `tau_cleav`'s "around 0.08" survived a tripling.

2. A figure from a non-converged fit is quoted. The strongest across-agent number in the
   whole series, +0.1308 with a CI excluding zero, comes from the 32-agent default fit
   whose worst seed gap is 0.7219 against a 0.3 threshold. It is the most attractive
   number the project has produced and it is not quotable.

3. The verdict collapses to a binary. "Positive and excludes zero" is not the same claim
   as "clears the declared bar", and the entire series so far lands between them.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import across_agent_trend as aat  # noqa: E402

ART = ROOT / "artifacts" / "across_agent_trend.json"


def _doc() -> dict:
    assert ART.exists(), "run `make across-agent-trend`"
    return json.loads(ART.read_text(encoding="utf-8"))


def test_the_declared_threshold_is_still_declared_where_it_was_declared() -> None:
    """Guard 1, as a direct check rather than through the script's own assertion."""
    text = (ROOT / "scripts" / "fit_forward.py").read_text(encoding="utf-8")
    assert aat.DECLARATION in re.sub(r"\s+", " ", text)
    assert f"+{aat.SUPPORT_THRESHOLD}" in aat.DECLARATION, (
        "the constant this script scores against is not the one the sentence names"
    )


def test_the_verdict_has_a_middle() -> None:
    """Guard 3. A positive figure short of the bar must not read as support."""
    assert aat._verdict(0.13, [0.074, 0.191]) == (
        "positive, excludes zero, below the declared bar"
    )
    assert aat._verdict(0.40, [0.1, 0.7]) == "supports the claim"
    assert aat._verdict(-0.05, [-0.2, 0.16]) == "indistinguishable from zero"
    assert aat._verdict(-0.30, [-0.5, -0.1]) == "negative, excludes zero"
    # A mean above the bar whose interval still straddles zero is not support either.
    assert aat._verdict(0.35, [-0.1, 0.8]) == "indistinguishable from zero"


def test_the_nonconverged_fit_is_flagged_not_quoted() -> None:
    """Guard 2. The warning has to name the fit, not merely exist."""
    doc = _doc()
    by_split = doc["strongest_figure_from_a_nonconverged_fit_by_split"]
    corpora = {r["corpus"]: r for r in doc["corpora"] if r["status"] == "present"}
    # The 32-agent default fit (worst seed gap 0.7219) carried the strongest figure until the
    # merged 65-agent fits landed; checked by hand on 2026-10-11, converged fits now lead both
    # splits (+0.2319 / +0.2066 against its +0.1308 on leave-one-agent-out). An empty flag is
    # then correct -- but only if a converged fit really leads, which is what is checked here,
    # so a flag that silently stopped working still fails.
    for split in ("leave_one_agent_out", "leave_one_family_out"):
        carriers = [r for r in corpora.values()
                    if r["splits"].get(split, {}).get("across_agent", {}).get("applicable")]
        if not carriers:
            continue
        best = max(carriers, key=lambda r: r["splits"][split]["across_agent"]["model_mean"])
        if best["converged"]:
            assert split not in by_split, f"{split}: flagged although a converged fit leads"
        else:
            assert split in by_split, (
                f"{split}: the strongest figure comes from {best['corpus']}, which did not "
                "converge, and the flag is missing"
            )
    assert corpora["expanded 32"]["converged"] is False, "the non-converged fit must stay marked"
    for split, flagged in by_split.items():
        assert flagged["split"] == split
        assert flagged["worst_seed_gap"] > 0.3
        assert corpora[flagged["corpus"]]["converged"] is False


def test_the_flag_belongs_to_the_split_it_is_filed_under() -> None:
    """The bug this key's shape exists to prevent, caught directly.

    One slot held by a loop over three splits keeps the last split's figure. The report
    block printed the family split's +0.0163 underneath the agent split's table, where
    the table's own largest value was +0.1308. A figure labelled as belonging to one table
    and taken from another is the defect section 9 opens with, written into the code that
    describes it.
    """
    doc = _doc()
    for split, flagged in doc["strongest_figure_from_a_nonconverged_fit_by_split"].items():
        row = next(r for r in doc["corpora"]
                   if r.get("corpus") == flagged["corpus"])
        assert row["splits"][split]["across_agent"]["model_mean"] == flagged["model_mean"], (
            f"the figure filed under {split} is not that split's value for "
            f"{flagged['corpus']}"
        )
        # And it is that split's maximum, not some other split's.
        carriers = [
            r for r in doc["corpora"]
            if r.get("status") == "present"
            and (r["splits"].get(split, {}).get("across_agent", {}) or {}).get("applicable")
        ]
        assert flagged["model_mean"] == max(
            r["splits"][split]["across_agent"]["model_mean"] for r in carriers
        )


def test_every_present_corpus_carries_its_convergence_state() -> None:
    """A row without it is a row whose figures cannot be read."""
    for row in _doc()["corpora"]:
        if row["status"] != "present":
            assert row["corpus"] and row["artefact"]
            continue
        assert isinstance(row["converged"], bool)
        assert row["worst_seed_gap"] >= 0
        assert row["n_agents"] > 0


def test_pending_corpora_are_named_rather_than_dropped() -> None:
    doc = _doc()
    listed = {r["corpus"] for r in doc["corpora"]}
    assert set(doc["pending"]) <= listed
    assert len(doc["corpora"]) == len(aat.CORPORA)


def test_the_trend_refuses_to_compute_on_too_few_points() -> None:
    few = [
        {"corpus": "a", "status": "present", "n_agents": 17, "converged": True,
         "on_expansion_path": True,
         "splits": {"leave_one_agent_out": {"delta_auc_mean": -0.1,
                                            "across_agent": {"applicable": True,
                                                             "model_mean": 0.0}}}},
    ]
    out = aat._trend(few, "leave_one_agent_out")
    assert out["computed"] is False and out["n_points"] == 1


def test_no_p_value_is_reported_below_five_points() -> None:
    """A rho of 1.0 over three points returns p = 0.0 from six possible orderings."""
    rows = [
        {"corpus": c, "status": "present", "n_agents": n, "converged": True,
         "on_expansion_path": True,
         "splits": {"leave_one_agent_out": {"delta_auc_mean": -0.1 * i,
                                            "across_agent": {"applicable": True,
                                                             "model_mean": 0.01 * i}}}}
        for i, (c, n) in enumerate([("a", 22), ("b", 26), ("c", 32)], start=1)
    ]
    out = aat._trend(rows, "leave_one_agent_out")
    assert out["computed"] is True and out["n_points"] == 3
    assert out["across_agent_vs_corpus_size"]["rho"] == 1.0
    assert out["across_agent_vs_corpus_size"]["p"] is None
    assert "five" in out["across_agent_vs_corpus_size"]["p_withheld_because"]


def test_a_nonconverged_fit_is_excluded_from_the_trend() -> None:
    """The trend is the claim this script exists to make, so it uses quotable fits only."""
    doc = _doc()
    t = doc["trends"]["leave_one_agent_out"]
    if not t.get("computed"):
        return
    converged = {
        r["n_agents"] for r in doc["corpora"]
        if r["status"] == "present" and r["converged"]
    }
    for pt in t["points"]:
        assert pt["n_agents"] in converged


def test_the_script_runs_and_rewrites_its_artefact() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/across_agent_trend.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "corpora have a fit on disk" in proc.stdout


def test_the_prediction_is_recorded_before_it_can_be_scored() -> None:
    """The project's rule: a prediction kept beside its result is the only useful kind."""
    pred = _doc()["prediction"]
    assert pred["made"] and pred["because"]
    assert set(pred["clauses"]) == {"positive", "ci_excludes_zero", "below_declared_bar"}
    if pred["outcome"] is None:
        assert all(v is None for v in pred["clauses"].values())
    else:
        assert all(isinstance(v, bool) for v in pred["clauses"].values())


def test_the_adjusted_figure_is_derived_from_the_fit_it_sits_beside() -> None:
    """Negative result 59, pinned.

    `--metrics` used to carry a fixed default pointing at the registry fit, so passing
    `--fold-predictions` from another corpus mixed that corpus's predictions with the
    registry fit's nuisance coefficients. The fix is that there is no default: the path is
    derived from the fold predictions. A default reintroduced here would be a hole that
    nothing else in the suite can see, because the default is the value nobody passes.
    """
    src = (ROOT / "scripts" / "across_agent_adjusted.py").read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", src)
    assert 'ap.add_argument("--metrics", type=Path, default=None,' in flat, (
        "--metrics has a default again; it has to be derived from --fold-predictions"
    )
    assert "args.fold_predictions.parent / \"forward_other_metrics.json\"" in src
    assert "--drop-uninformative-absences" in src, (
        "without this flag the adjusted figure cannot be computed for any "
        "absences-dropped fit: the corpus guard refuses and nothing can satisfy it"
    )


def test_the_adjusted_artefact_agrees_with_the_fit_beside_it() -> None:
    """The producing script asserts this; the test states what it is asserting."""
    doc = _doc()
    for row in doc["corpora"]:
        if row.get("status") != "present" or not row.get("adjusted"):
            continue
        assert row["adjusted"]["n_agents"] == row["n_agents"]


def test_an_off_path_corpus_is_listed_and_excluded() -> None:
    """Computed, not declared: a fit whose grid does not contain the baseline's.

    `artifacts/with_literature` reports 17 agents and is neither a subset nor a superset of
    the 22-agent registry grid. Its agent count is a different quantity with the same name,
    so putting it on a size axis labels a difference in composition as one in size.
    """
    doc = _doc()
    off = [r for r in doc["corpora"]
           if r.get("status") == "present" and not r.get("on_expansion_path")]
    assert off, "no present corpus is off the expansion path; check the chain computation"
    for r in off:
        assert r["off_path_reason"], f"{r['corpus']} is excluded with no reason recorded"
    excluded = {r["n_agents"] for r in off}
    for split, tr in doc["trends"].items():
        for pt in tr.get("points", []):
            assert pt["n_agents"] not in excluded, (
                f"{split}'s trend includes an off-path corpus's agent count"
            )


def test_the_chain_is_recomputed_rather_than_asserted() -> None:
    """The exclusion must come from the frames, not from a literal in the script."""
    src = (ROOT / "scripts" / "across_agent_trend.py").read_text(encoding="utf-8")
    assert "def _agents(" in src and "ds.load(" in src, (
        "the expansion-path check no longer loads the corpora; a hand-maintained flag is "
        "one more thing to keep true"
    )
    assert "SUPERSEDED_REASON" not in src, "the hand-maintained flag is back"
