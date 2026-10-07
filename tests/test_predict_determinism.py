"""A design's predicted risk must not depend on what else was asked about.

The agent-variation term drew an (n_draws, n_designs) matrix from one seed, so a design's
deviation depended on its position in the batch and on the batch size. Measured before the
fix: the same design's mean rate moved by up to 0.0074 absolute -- three quarters of a
percentage point -- between a five-design call and a hundred-and-six-design one.

Two distinct harms. A caller asking about a few designs got different numbers from one
asking about many, for the same design. And inside a single response, `score_designs` runs
on the designs that passed while `why_not_the_obvious_one` runs on all of them, so the two
halves of the comparison the response draws carried different noise for the same candidate.
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest

from adctox.model.predict import Posterior, predict_draws

ART = Path(__file__).resolve().parents[1] / "artifacts"
pytestmark = pytest.mark.skipif(
    not (ART / "posterior_other.npz").exists(), reason="no posterior built"
)


@pytest.fixture(scope="module")
def post():
    return Posterior.load(ART / "posterior_other.npz")


def _draw(post, designs):
    return predict_draws(
        post,
        mechanisms=[m for m, _, _ in designs],
        families=[f for _, f, _ in designs],
        dars=np.array([d for _, _, d in designs]),
        cleavables=np.ones(len(designs)),
    )


def _fleet(post, n):
    fams = [f for f in post.families[:3]] or ["camptothecin"]
    mech_of = {}
    for i, m in enumerate(post.mechanisms):
        mech_of[m] = m
    out = []
    for i in range(n):
        m = post.mechanisms[i % len(post.mechanisms)]
        out.append((m, fams[i % len(fams)], 2.0 + (i % 7)))
    return out


def test_a_design_is_invariant_to_batch_size(post):
    fleet = _fleet(post, 60)
    small = _draw(post, fleet[:5])
    large = _draw(post, fleet)[:, :5, :]
    assert np.abs(small - large).max() == 0.0, (
        "the same design predicts differently depending on how many designs were asked "
        "about alongside it"
    )


def test_a_design_is_invariant_to_batch_order(post):
    fleet = _fleet(post, 40)
    order = list(range(len(fleet)))
    random.Random(1).shuffle(order)
    straight = _draw(post, fleet)
    shuffled = _draw(post, [fleet[i] for i in order])
    restored = np.empty_like(shuffled)
    for new, orig in enumerate(order):
        restored[:, orig, :] = shuffled[:, new, :]
    assert np.abs(straight - restored).max() == 0.0


def test_identical_slots_share_one_deviation(post):
    """Two designs with the same slots are the same molecule, so one agent effect."""
    d = _draw(post, [(post.mechanisms[0], post.families[0], 4.0)] * 2)
    assert np.array_equal(d[:, 0, :], d[:, 1, :])


def test_deviations_stay_standard_normal_and_near_independent(post):
    """Seeding per design must not disturb what the term is for.

    If hashing introduced structure, the agent term would stop being a draw from the
    fitted residual distribution and the intervals would be wrong in an unknown direction.
    """
    n = 400
    mech = [post.mechanisms[0]] * n
    fam = [post.families[0]] * n
    dars = np.linspace(2.0, 8.0, n)
    cle = np.ones(n)
    with_var = predict_draws(post, mechanisms=mech, families=fam, dars=dars, cleavables=cle)
    without = predict_draws(
        post, mechanisms=mech, families=fam, dars=dars, cleavables=cle,
        include_agent_variation=False,
    )
    lw = np.log(with_var / (1 - with_var))
    ln = np.log(without / (1 - without))
    dev = (lw - ln)[:, :, 0] / post.sigma_agent[:, None]
    assert abs(dev.mean()) < 0.05, f"deviation mean {dev.mean():.4f} is not ~0"
    assert 0.9 < dev.std() < 1.1, f"deviation sd {dev.std():.4f} is not ~1"
    corr = np.corrcoef(dev[:, :8].T)
    off = corr[~np.eye(8, dtype=bool)]
    assert np.abs(off).max() < 0.4, (
        f"deviations across designs correlate at {np.abs(off).max():.2f}; the per-design "
        "seeding has introduced structure"
    )


def test_turning_the_term_off_narrows_the_interval(post):
    """The term exists to widen a new molecule's interval; check it does."""
    fleet = _fleet(post, 6)
    wide = _draw(post, fleet)
    narrow = predict_draws(
        post,
        mechanisms=[m for m, _, _ in fleet],
        families=[f for _, f, _ in fleet],
        dars=np.array([d for _, _, d in fleet]),
        cleavables=np.ones(len(fleet)),
        include_agent_variation=False,
    )
    w = np.percentile(wide, 95, axis=0) - np.percentile(wide, 5, axis=0)
    n = np.percentile(narrow, 95, axis=0) - np.percentile(narrow, 5, axis=0)
    # Stated as a tendency, not a per-cell guarantee: these are empirical percentiles over
    # a few hundred draws, so an individual cell can narrow by chance even though adding
    # an independent term widens the distribution. Asserting every cell was wrong, and
    # would have failed intermittently rather than meaning anything.
    assert w.mean() > n.mean() * 1.2, (
        f"the agent term barely widens anything: mean width {w.mean():.4f} with, "
        f"{n.mean():.4f} without"
    )
    frac_wider = float((w > n).mean())
    assert frac_wider > 0.9, f"only {100 * frac_wider:.0f}% of cells widened"
