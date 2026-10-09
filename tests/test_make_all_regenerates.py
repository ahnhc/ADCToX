"""Every script that writes an artefact the report quotes must be in `make all`.

The report opens by claiming that `make all` regenerates every number in it. Two targets
added today were not in `all` while their figures were quoted -- `row-grade-exposure`, which
bounds the grade-in-the-row-label exposure at 6 of 2,696 observations, and `dar-gap`, which
reports that 1,471 harvested articles recover 2 of the 12 missing drug-to-antibody ratios.
Nothing noticed, because the number guard checks that a figure traces to an artefact *on
disk* and cannot tell whether a clean tree would still produce that artefact.

So the invariant is mechanical: a script that writes under `artifacts/` is either reachable
from `make all` or explicitly exempted here with a reason. There are four exemptions: the
inverse-retrieval evaluation, which refits a posterior per held-out agent and takes about
four hours, so `make expensive` carries it the way `make fetch` carries the network steps.
The rest are reachable from `all`.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Scripts that write an artefact and are deliberately outside `all`.
# Scripts that write an artefact and are deliberately outside `all`. One, and it says why.
EXEMPT = {
    # One posterior refit per held-out agent, about four hours. `make expensive` carries it,
    # the way `make fetch` carries the network steps, and `all` is meant to be runnable.
    "inverse_retrieval.py",
    # Needs the expanded corpus's posterior, which is a separate multi-hour fit. It answers
    # a decision rather than producing a report figure: whether the product's output moves
    # between the two posteriors, which is what makes the serving choice measurable.
    "posterior_choice.py",
    # Both read the teammate-supplied workbook, which is not redistributed: `data/raw/` is
    # gitignored and only the hash is recorded, the same posture the MedDRA dictionary uses.
    # `make all` has to be runnable from a clone, so these cannot be in it. The ingest is
    # reproducible from the workbook by `make atlas-ingest merged-scale`, and
    # docs/TEAMMATE_DATA_USE.md records what it does.
    "ingest_atlas_db.py",
    "merged_corpus_scale.py",
    "merge_atlas_corpus.py",
    "precedent_audit.py",
}
def _scripts_writing_artefacts() -> set[str]:
    out = set()
    for path in sorted((ROOT / "scripts").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "write_json(" in text or re.search(r'artifacts["\'/]', text):
            out.add(path.name)
    return out


def _scripts_in_make_all() -> set[str]:
    proc = subprocess.run(
        ["make", "-n", "all"], cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return set(re.findall(r"scripts/([a-z_0-9]+\.py)", proc.stdout))


def test_every_artefact_writing_script_is_reachable_from_make_all() -> None:
    writing = _scripts_writing_artefacts()
    reached = _scripts_in_make_all()
    missing = sorted(writing - reached - EXEMPT)
    assert not missing, (
        "these write artefacts the report may quote and are not in `make all`: "
        f"{missing}. Add the target to `all`, or add the script to EXEMPT with the reason."
    )


def test_the_exemption_list_names_only_scripts_that_exist() -> None:
    """An exemption for a deleted script is an exemption that hides its replacement."""
    present = {p.name for p in (ROOT / "scripts").glob("*.py")}
    stale = sorted(EXEMPT - present)
    assert not stale, f"exemptions for scripts that no longer exist: {stale}"


# The measurement targets that read the fit's artefacts rather than producing them. Running
# any one of these should cost seconds.
MEASUREMENT_TARGETS = [
    "residual-scale", "across-agent", "design-effects", "fold-difficulty", "hard-flags",
    "comorbidity-sensitivity", "payload-compression",
]


def test_a_measurement_target_does_not_refit_the_model() -> None:
    """Twice now, running one measurement has silently refit the whole model.

    First because the targets depended on `forward`, which is `.PHONY`, so make rebuilt it
    unconditionally. That was fixed by depending on the metrics *file* instead -- and the
    fix did nothing, because the variable holding its path was defined one line above
    `ART := artifacts` and `:=` expands immediately, making the prerequisite
    `/forward_other_metrics.json`: a path at the filesystem root that never exists. Make
    rebuilt it every time, exactly as before, so the symptom was unchanged and the fix
    looked like it had failed to apply.

    Neither failure is visible from inside `make all`, where the fit runs once anyway. It
    costs about an hour per invocation outside it, and it silently overwrites the artefacts
    the report's figures are checked against while a session is working on them.
    """
    for target in MEASUREMENT_TARGETS:
        proc = subprocess.run(
            ["make", "-n", target], cwd=ROOT, capture_output=True, text=True,
        )
        assert proc.returncode == 0, (target, proc.stderr[-500:])
        assert "fit_forward.py" not in proc.stdout, (
            f"`make {target}` would run fit_forward.py:\n{proc.stdout}\n"
            "Its prerequisite does not resolve to a file on disk. Check that "
            "FORWARD_METRICS is defined after ART."
        )


def test_the_metrics_prerequisite_resolves_to_a_real_path() -> None:
    """The root cause, caught directly rather than through its symptom.

    A prerequisite of `/something` is not a typo make will complain about: it is a perfectly
    valid path that simply never exists, so the only signal is an hour of wasted compute.
    """
    proc = subprocess.run(
        ["make", "-n", "--print-data-base", "residual-scale"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert "FORWARD_METRICS = artifacts/forward_other_metrics.json" in proc.stdout or \
           "FORWARD_METRICS := artifacts/forward_other_metrics.json" in proc.stdout, (
        "FORWARD_METRICS does not expand to a path under artifacts/; a `:=` assignment "
        "above `ART := artifacts` expands it to the filesystem root."
    )
