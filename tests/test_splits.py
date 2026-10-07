"""Cross-validation folds must leak nothing and discard nothing.

Two bugs lived here at once, pulling the reported numbers in opposite directions.

  * The family and mechanism splits dropped held-out *arms* but not held-out *trials*,
    so NCT03529110 -- a T-DXd vs T-DM1 head-to-head, named in the module docstring as
    the reason whole trials must go -- left the comparator arm in training. The held-out
    arm then inherited a trial-level random intercept fitted from its own comparator.
    That flatters the held-out prediction.
  * leave-one-agent-out masked on the raw trial index. Single-arm trials are collapsed
    onto one sentinel index, so holding out any agent with a single-arm trial put the
    sentinel into the excluded set and discarded all 128 sentinel arms -- arms from
    unrelated agents whose only shared property is carrying no trial effect. Measured,
    folds trained on about half the arms they should have: 125 of 285 for T-DM1 against
    236 after the fix, 1,980 arm-folds discarded across the sixteen folds. That depresses
    the held-out prediction.

So one split was optimistic and the other pessimistic, and the same line of code was
responsible for both.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from adctox.model import dataset as ds, splits
from adctox.taxonomy import default_taxonomy

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"


@pytest.fixture(scope="module")
def data():
    if not (PROCESSED / "arms.parquet").exists():
        pytest.skip("corpus not built")
    return ds.load(PROCESSED, list(default_taxonomy().axis_order), kind="other")


def _carries(data):
    return np.asarray(data.arm_has_trial_effect).astype(bool)


ALL_SPLITS = [
    ("leave_one_agent_out", splits.leave_one_agent_out),
    ("leave_one_family_out", splits.leave_one_family_out),
    ("leave_one_mechanism_out", splits.leave_one_mechanism_out),
]


@pytest.mark.parametrize("name, fn", ALL_SPLITS)
def test_no_trial_effect_is_shared_across_a_fold(data, name, fn):
    """The leak that mattered. Only arms carrying a trial effect can leak one, so the
    check is restricted to those; counting the sentinel would report false leaks."""
    carries = _carries(data)
    for fold in fn(data):
        train = {a for a in np.unique(data.arm_idx[fold.train_cells]) if carries[a]}
        test = {a for a in np.unique(data.arm_idx[fold.test_cells]) if carries[a]}
        shared = (
            {int(data.arm_trial_idx[a]) for a in train}
            & {int(data.arm_trial_idx[a]) for a in test}
        )
        assert not shared, (
            f"{name}/{fold.name}: trials {[data.trials[t] for t in shared]} appear on "
            "both sides, so the held-out arm inherits a trial effect fitted from its own "
            "trial"
        )


@pytest.mark.parametrize("name, fn", ALL_SPLITS)
def test_train_and_test_cells_are_disjoint(data, name, fn):
    for fold in fn(data):
        assert not (fold.train_cells & fold.test_cells).any(), f"{name}/{fold.name}"
        assert fold.train_cells.any() and fold.test_cells.any(), f"{name}/{fold.name}"


@pytest.mark.parametrize("name, fn", ALL_SPLITS)
def test_the_held_out_identity_never_survives_in_training(data, name, fn):
    idx = {
        "agent": data.arm_agent_idx,
        "family": data.arm_family_idx,
        "mechanism": data.arm_mech_idx,
    }
    labels = {"agent": data.agents, "family": data.families, "mechanism": data.mechanisms}
    for fold in fn(data):
        arms = np.unique(data.arm_idx[fold.train_cells])
        names = {labels[fold.kind][int(idx[fold.kind][a])] for a in arms}
        assert fold.name not in names, f"{name}: {fold.name} survives in its own training set"


def test_single_arm_trials_are_not_swept_out_with_the_sentinel(data):
    """The discard bug, pinned by its mechanism rather than by a magic number.

    Arms carrying no trial effect share one index. They can neither leak a trial effect
    nor receive one, so holding out an agent must not remove the other agents' sentinel
    arms from training.
    """
    carries = _carries(data)
    sentinel_arms = np.where(~carries)[0]
    assert len(sentinel_arms) > 50, "premise changed: few arms lack a trial effect"
    for fold in splits.leave_one_agent_out(data):
        ai = list(data.agents).index(fold.name)
        train = set(np.unique(data.arm_idx[fold.train_cells]))
        others = [a for a in sentinel_arms if data.arm_agent_idx[a] != ai]
        kept = sum(1 for a in others if a in train)
        assert kept == len(others), (
            f"{fold.name}: {len(others) - kept} of {len(others)} other agents' "
            "effect-free arms were dropped from training; the sentinel index is being "
            "treated as a real trial"
        )


def test_folds_keep_most_of_the_corpus(data):
    """A fold that trains on half the corpus is a different experiment from the one
    reported, and nothing else here would notice."""
    n_arms = len(data.arm_agent_idx)
    for name, fn in ALL_SPLITS:
        for fold in fn(data):
            trained = len(np.unique(data.arm_idx[fold.train_cells]))
            held = len(np.unique(data.arm_idx[fold.test_cells]))
            floor = 0.45 if name == "leave_one_mechanism_out" else 0.70
            assert trained >= floor * (n_arms - held), (
                f"{name}/{fold.name} trains on {trained} of {n_arms - held} available "
                f"arms, below the {floor:.0%} floor"
            )
