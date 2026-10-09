"""Three defects in the ranking layer, each of which the whole suite missed.

The product's central promise about uncertainty is that it does not rank designs it cannot
separate. Every one of these bugs broke that promise in a different direction, and 413
passing tests covered none of them -- there was no test that two identical candidates share
a rank, that grouping is not transitive, or that a dominated candidate is never displayed
in place of a non-dominated one.

1. `P(a < b)` reads an exact tie as a loss. Exact ties are the normal case here, not a
   corner: the model carries no term separating DM1 from DM4, both maytansinoids on the
   same linker, so their draws are identical. The strict comparison returned 0.0, which
   `min(p, 1-p)` read as decisive separation -- so the two were printed as rank 1 and rank
   2 while pairs that genuinely overlapped at P = 0.53 were correctly merged.
2. Grouping chained on adjacent pairs, which is transitive. A ~ B and B ~ C put A and C in
   one group however far apart they are, and on a real query all 74 candidates collapsed
   into a single set.
3. The displayed candidates were the first `top_k` of the ordering. Once the head group is
   large that order is a secondary preference, and it showed three dominated designs while
   hiding five non-dominated ones.
"""

from __future__ import annotations

import numpy as np
import pytest

from adctox.design.enumerate import Design
from adctox.design.search import ScoredDesign, _p_better, rank_and_group

RNG = np.random.default_rng(0)


def _design(payload: str, dar: float = 2.0) -> Design:
    return Design(
        target="HER2", payload=payload, mechanism="tubulin", linker="SMCC",
        cleavable=False, conjugation="lysine", dar=dar, isotype="IgG1", masking="none",
    )


def _scored(payload: str, draws: np.ndarray, o2: float = 0.5,
            o3: float = 1.0, o2w: float | None = None) -> ScoredDesign:
    """`o2w` is the patient-weighted worst organ, which is what orders a tie group.

    It defaults to the unweighted value so a test that does not care about the weighting
    reads as before; a test about the ordering inside a group passes the two separately,
    because that is the distinction negative result 40 turns on.
    """
    return ScoredDesign(
        design=_design(payload),
        organ_risk={}, organ_interval={},
        o1_weighted_risk=float(draws.mean()),
        o2_worst_axis_risk=o2, o2_worst_axis="hepatic",
        o2_weighted_worst_axis_risk=o2 if o2w is None else o2w,
        o2_weighted_worst_axis="hepatic",
        o3_precedent=o3,
        binding_constraint=None, draws_o1=draws,
    )


def test_identical_candidates_share_a_rank() -> None:
    """The first defect, at its root. Two designs with the same draws must not be printed
    as first and second place."""
    draws = RNG.normal(0.3, 0.05, 2000)
    a = _scored("DM1", draws)
    b = _scored("DM4", draws.copy())
    ordered, _, groups = rank_and_group([a, b])

    assert _p_better(draws, draws.copy()) == pytest.approx(0.5)
    assert groups == [[0, 1]], groups
    assert ordered[0].rank == ordered[1].rank == 1
    assert ordered[0].distinguishable is False
    assert ordered[0].group_size == 2


def test_a_tie_is_never_read_as_a_loss() -> None:
    """The mechanism, isolated. A strict `(a < b).mean()` is 0.0 for an exact tie, which is
    the value a decisive *loss* also takes, and the two cannot be told apart downstream."""
    x = np.linspace(0.1, 0.4, 500)
    assert float((x < x).mean()) == 0.0           # the old behaviour
    assert _p_better(x, x) == pytest.approx(0.5)  # the fixed one
    assert _p_better(x, x + 1.0) == pytest.approx(1.0)
    assert _p_better(x + 1.0, x) == pytest.approx(0.0)


def test_grouping_is_not_transitive() -> None:
    """The second defect. Three candidates where neighbours overlap but the ends do not:
    chaining on adjacent pairs puts all three in one group, which asserts that the best and
    the worst are indistinguishable when the best beats the worst on every draw."""
    # Independent draws on purpose, and the spacing is chosen rather than guessed. A
    # shifted *copy* of one array is perfectly correlated with it, so its comparison is
    # decided at every draw -- the first version of this test asserted its own premise
    # wrongly that way. And a far-away third candidate is split by adjacent chaining too,
    # so it would not have caught the defect either. For unit-variance independent draws
    # spaced by d, P(a beats b) is Phi(d / sqrt(2)); the chain survives a step only while
    # that stays under 0.65, and the ends must exceed it at 2d. Both hold for d in
    # (0.272, 0.545), and d = 0.42 sits in the middle of it: adjacent P = 0.617, ends
    # P = 0.724.
    d, n = 0.42, 20_000
    a = _scored("A", RNG.normal(0.0, 1.0, n))
    b = _scored("B", RNG.normal(d, 1.0, n))
    c = _scored("C", RNG.normal(2 * d, 1.0, n))

    # The premise, asserted rather than assumed.
    p_ab = _p_better(a.draws_o1, b.draws_o1)
    p_bc = _p_better(b.draws_o1, c.draws_o1)
    p_ac = _p_better(a.draws_o1, c.draws_o1)
    assert min(p_ab, 1 - p_ab) > 0.35, p_ab
    assert min(p_bc, 1 - p_bc) > 0.35, p_bc
    assert min(p_ac, 1 - p_ac) < 0.35, p_ac

    _, _, groups = rank_and_group([a, b, c])
    heads = [g for g in groups if 0 in g]
    assert heads, groups
    assert 2 not in heads[0], (
        "A and C are in one tie group although A beats C decisively; the grouping chained "
        "through B"
    )


def test_a_dominated_candidate_is_not_shown_over_a_non_dominated_one() -> None:
    """The third defect, through the pipeline, because it lives in the display selection
    rather than in the ranking. Any candidate the response shows while a non-dominated one
    goes unshown is the failure."""
    from adctox.api.main import _posterior, _serious_posterior
    from adctox.pipeline import propose

    out = propose(
        target_antigen="HER2",
        condition_ids=["ckd_stage_4_5", "interstitial_lung_disease"],
        posterior=_posterior(), top_k=6, serious_posterior=_serious_posterior(),
    )
    shown = out["candidates"]
    assert len(shown) == 6
    on_front = [c["on_pareto_front"] for c in shown]
    # More non-dominated candidates exist than fit, so every shown one must be one.
    assert out["n_pareto_front"] >= len(shown)
    assert all(on_front), on_front
    assert out["pareto_front"] == list(range(len(shown)))


def test_a_large_head_group_says_what_orders_it() -> None:
    """A group of 49 cannot be presented as a ranking, and something still has to order the
    six cards. The response must name that criterion rather than let a reader take the
    order for confidence."""
    from adctox.api.main import _posterior, _serious_posterior
    from adctox.pipeline import propose

    out = propose(
        target_antigen="HER2",
        condition_ids=["ckd_stage_4_5", "interstitial_lung_disease"],
        posterior=_posterior(), top_k=6, serious_posterior=_serious_posterior(),
    )
    head = out["candidates"][0]
    if head["group_size"] and head["group_size"] > 1:
        assert head["secondary_order_basis"], (
            "a tied group is displayed in some order and does not say which"
        )
        assert head["distinguishable"] is False
        assert all(c["rank"] == head["rank"] for c in out["candidates"]
                   if c["tie_group"] == head["tie_group"])


def test_the_shown_set_spans_the_payloads_on_the_front() -> None:
    """A fourth defect in the same place, found by looking at what the cards actually said.

    With the front selected but ordered by the secondary preference, the six cards were
    DGN549 twice, DM1 twice and DM4 twice -- three of the front's six payloads, and two of
    those pairs are designs this model cannot separate at all -- while MMAE, MMAF and the
    pyrrolobenzodiazepine never appeared despite being non-dominated. Six cards showing
    three payloads, two of them doubled, is a worse answer than six showing six.
    """
    from adctox.api.main import _posterior, _serious_posterior
    from adctox.pipeline import propose

    import adctox.design.search as search
    import adctox.pipeline as pipeline

    captured = {}
    original = search.rank_and_group

    def spy(scored, **kw):
        out = original(scored, **kw)
        captured["ordered"], captured["pareto"] = out[0], out[1]
        return out

    search.rank_and_group = spy
    pipeline.rank_and_group = spy
    try:
        out = propose(
            target_antigen="ERBB2",
            condition_ids=["ckd_stage_4_5", "interstitial_lung_disease"],
            posterior=_posterior(), top_k=6, serious_posterior=_serious_posterior(),
        )
    finally:
        search.rank_and_group = original
        pipeline.rank_and_group = original

    shown = out["candidates"]
    payloads = [c["design"]["payload"] for c in shown]
    on_front = {
        captured["ordered"][i].design.payload for i in captured["pareto"]
    }
    # The property the rule guarantees: every payload on the front is shown, and a repeat
    # happens only after they are exhausted. Asserting all six distinct would be asserting
    # that the front always has at least six payloads, which it does not -- here it has
    # five, so the sixth slot must repeat one of them.
    assert on_front <= set(payloads), sorted(on_front - set(payloads))
    assert len(set(payloads)) == min(len(on_front), len(shown)), (
        sorted(on_front), payloads
    )
    assert out["shown_selection"], "the selection rule is not stated"
    # And it is still the front that is drawn from, not merely a diverse sample.
    assert all(c["on_pareto_front"] for c in shown)
