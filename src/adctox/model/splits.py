"""Cross-validation folds that respect the corpus's nesting.

The nesting is trial < agent < (mechanism x target), and it is total: every design
feature is constant within an agent. Consequences, both load-bearing:

* A random split over arms leaks catastrophically. One agent contributes up to 48 arms,
  so a random fold trains and tests on the same molecule.
* Splitting at *agent* level is the realistic deployment question ("a new ADC, known
  chemistry") but still leaks the mechanism, because mechanism and agent are nearly
  collinear -- 4 vedotins share MMAE.
* Splitting at *mechanism* level is the question the product actually makes a claim
  about, and it is only answerable for mechanisms carrying at least 3 agents. Measured
  on this corpus: tubulin (7 agents) and topo1 (4) qualify; dna_cleave (2),
  dna_crosslink (2), dna_alkyl (1) and protein_synth (1) do not, and that does not
  improve with corpus size -- only two calicheamicin ADCs have ever been approved
  anywhere, and one immunotoxin.

A further leak worth naming: NCT03529110 is a T-DXd vs T-DM1 head-to-head. Holding out
T-DXd while training on the T-DM1 arm of the *same* trial shares the antibody, the
target, the population and the reporting threshold. Worse than sharing covariates, the
held-out arm inherits a trial-level random intercept fitted from its own comparator arm.
So every split drops whole trials, not just arms.

That last sentence was false for a while, and the module said it anyway: only
leave-one-agent-out dropped shared trials, while the family and mechanism splits dropped
arms. Measured, counting only the 157 arms that carry a trial effect at all:
leave-one-agent-out leaked 0 trials, and the family and mechanism splits leaked 2 each --
every one of them NCT03529110, the trial named above. The leak flatters the held-out
predictions, so the family and mechanism deltas were, if anything, optimistic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from .dataset import ModelData


@dataclass(frozen=True)
class Fold:
    name: str
    kind: str                   # 'agent' | 'mechanism'
    train_cells: np.ndarray     # boolean mask over cells
    test_cells: np.ndarray
    held_mech_idx: int | None   # set for mechanism folds, so the model can zero it out
    held_family_idx: int | None = None


def _cells_for_arms(data: ModelData, arm_mask: np.ndarray) -> np.ndarray:
    return arm_mask[data.arm_idx]


def _drop_whole_trials(data: ModelData, held: np.ndarray) -> np.ndarray:
    """Arms to exclude from training: the held-out arms and every arm sharing a trial.

    Only arms that carry a trial effect can leak one, and single-arm trials are collapsed
    onto a shared sentinel index, so masking on the raw index would exclude all 128 of
    them from every fold and gut the training set for no reason.
    """
    carries = np.asarray(data.arm_has_trial_effect).astype(bool)
    shared = {
        int(t) for t in np.unique(data.arm_trial_idx[held & carries]).tolist()
    }
    if not shared:
        return held
    same_trial = np.isin(data.arm_trial_idx, list(shared)) & carries
    return held | same_trial


def leave_one_agent_out(data: ModelData, drop_shared_trials: bool = True) -> list[Fold]:
    """One fold per agent. Also drops every trial the agent appears in (see module note)."""
    folds: list[Fold] = []
    for ai, agent in enumerate(data.agents):
        is_agent = data.arm_agent_idx == ai
        test_arms = is_agent
        excluded = _drop_whole_trials(data, is_agent) if drop_shared_trials else is_agent
        train_arms = ~excluded
        if not train_arms.any() or not test_arms.any():
            continue
        folds.append(
            Fold(
                name=agent,
                kind="agent",
                train_cells=_cells_for_arms(data, train_arms),
                test_cells=_cells_for_arms(data, test_arms),
                held_mech_idx=None,
            )
        )
    return folds


def leave_one_family_out(data: ModelData, min_agents: int = 2) -> list[Fold]:
    """One fold per payload family carrying at least `min_agents` agents.

    Family is the resolution the failure analysis points at, and a lower agent floor is
    defensible here than for mechanism because the question is narrower: can the model
    predict a family from its *siblings inside the same mechanism*, rather than from
    nothing. Families below the floor are skipped, as for mechanism.
    """
    agents_per_family: dict[int, set[int]] = {}
    for fi, ai in zip(data.arm_family_idx, data.arm_agent_idx):
        agents_per_family.setdefault(int(fi), set()).add(int(ai))
    folds: list[Fold] = []
    for fi, agent_set in sorted(agents_per_family.items()):
        if len(agent_set) < min_agents:
            continue
        is_fam = data.arm_family_idx == fi
        folds.append(
            Fold(
                name=data.families[fi],
                kind="family",
                train_cells=_cells_for_arms(data, ~_drop_whole_trials(data, is_fam)),
                test_cells=_cells_for_arms(data, is_fam),
                held_mech_idx=None,
                held_family_idx=fi,
            )
        )
    return folds


def leave_one_mechanism_out(data: ModelData, min_agents: int = 3) -> list[Fold]:
    """One fold per mechanism carrying at least `min_agents` distinct agents.

    Mechanisms below the floor are skipped rather than reported as weak folds: removing
    the class removes the only agent carrying the level, so there is no coefficient left
    to predict with and the resulting number would be noise presented as a result.
    """
    per_mech: Counter[int] = Counter()
    for mi, ai in zip(data.arm_mech_idx, data.arm_agent_idx):
        per_mech[int(mi)] = per_mech.get(int(mi), 0)
    agents_per_mech: dict[int, set[int]] = {}
    for mi, ai in zip(data.arm_mech_idx, data.arm_agent_idx):
        agents_per_mech.setdefault(int(mi), set()).add(int(ai))

    folds: list[Fold] = []
    for mi, agent_set in sorted(agents_per_mech.items()):
        if len(agent_set) < min_agents:
            continue
        is_mech = data.arm_mech_idx == mi
        folds.append(
            Fold(
                name=data.mechanisms[mi],
                kind="mechanism",
                train_cells=_cells_for_arms(data, ~_drop_whole_trials(data, is_mech)),
                test_cells=_cells_for_arms(data, is_mech),
                held_mech_idx=mi,
                # A held-out mechanism's families are held out with it; otherwise the
                # family term would leak the very chemistry the fold removed.
                held_family_idx=None,
            )
        )
    return folds


def fold_report(data: ModelData, min_agents: int = 3) -> str:
    agents_per_mech: dict[int, set[int]] = {}
    arms_per_mech: Counter[int] = Counter()
    for mi, ai in zip(data.arm_mech_idx, data.arm_agent_idx):
        agents_per_mech.setdefault(int(mi), set()).add(int(ai))
        arms_per_mech[int(mi)] += 1
    lines = [f"  {'mechanism':16s} {'arms':>5s} {'agents':>7s}  fold"]
    for mi, names in sorted(agents_per_mech.items()):
        n = len(names)
        verdict = "VIABLE" if n >= min_agents else f"skipped (<{min_agents} agents)"
        lines.append(
            f"  {data.mechanisms[mi]:16s} {arms_per_mech[mi]:5d} {n:7d}  {verdict}"
        )
    return "\n".join(lines)
