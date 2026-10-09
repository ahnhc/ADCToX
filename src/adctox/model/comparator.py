"""Where one design's predicted rate sits among the chemistries that have been built.

A rate alone is close to unreadable. "Gastrointestinal 0.59, high" says less than "higher
than 29 of the 32 ADC chemistries in this corpus", and the plan asked for exactly that and
banned percentiles: a percentile on a sample of 32 invents resolution the sample cannot
carry, so the comparator is an ordinal position with its denominator printed beside it.

What it is: the same model's prediction for the *slots* of every ADC in the registry whose
chemistry is fully stated, with the agent-level residual switched off, ranked against the
queried design's prediction. Design against design, on one footing.

Registry and not corpus. Five of the 22 reference chemistries -- depatuxizumab mafodotin,
disitamab vedotin, farletuzumab ecteribulin, rovalpituzumab tesirine and sacituzumab
tirumotecan -- are absent from the 16-agent fit, so their rates are out-of-corpus
predictions exactly as the queried design's is. That is the consistent footing, and calling
them "corpus chemistries" would have been wrong; where the posterior records which agents it
saw, the comparison reports the split.

What it is not: a comparison against what those agents were observed to do. The posterior
integrates out the per-agent effect, so an agent's fitted rate cannot be recovered from it,
and the observed rates are censored at each trial's reporting cut, which leaves "higher
than" undefined for a large share of cells. A model-against-model rank is the claim the
available quantities support.

Nor is it a fine distinction. The across-agent ranking this inherits its meaning from
correlates with the observed ranking at about 0.17 per axis after the reporting conditions
are removed from both series, so only the extremes carry information.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from .predict import Posterior, predict_draws

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "conf" / "adc_registry.yaml"


def _registry_designs(path: Path = REGISTRY) -> tuple[list[dict], int]:
    """Conventional conjugates whose slots are complete enough to predict from.

    An agent with no stated DAR is excluded rather than given the corpus mean. Substituting
    a mean would place it at the centre of the comparison on the strength of a missing
    value, and 11 of the 16 agents added by the name-stem sweep have no DAR in any source --
    enough to move a rank on their own.
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))["agents"]
    out = []
    n_conventional = 0
    for key, spec in doc.items():
        if not spec.get("conventional_adc"):
            continue
        n_conventional += 1
        if spec.get("dar") is None or not spec.get("mechanism"):
            continue
        out.append({
            # The registry key, which is what `Posterior.agents` and the corpus frames use.
            # Carried beside the INN because the two are different strings -- "brentuximab
            # vedotin" against `brentuximab_vedotin` -- and matching the display name
            # against the fitted agent list gave an intersection of zero, reporting that
            # none of the references was in the fit when 17 of 22 were.
            "key": key,
            "inn": spec["inn"],
            "mechanism": spec["mechanism"],
            "family": spec.get("payload_family") or "",
            "dar": float(spec["dar"]),
            "cleavable": bool(spec.get("linker_cleavable")),
        })
    # Both counts. Returning only the usable list made the "excluded" figure in the
    # comparator a difference between two already-filtered numbers, which is always zero --
    # it reported that nothing had been excluded while silently dropping twelve agents.
    return out, n_conventional


# Cached on the posterior's identity. A `Posterior` holds numpy arrays and is therefore
# unhashable, so `lru_cache` cannot key on it; the cache keeps a reference to the object
# alongside the result, which both pins the identity against reuse after collection and
# makes the entry's lifetime the posterior's. The registry and the fit are fixed for the
# life of a process, and recomputing 30-odd predictions per request would put a Monte Carlo
# draw on the serving path for a number that never changes.
_CACHE: dict[int, tuple[Posterior, np.ndarray, list[str], int, list[str]]] = {}


def _reference_matrix(
    post: Posterior,
) -> tuple[np.ndarray, list[str], int, list[str]]:
    """(n_agents, n_axes) posterior-mean rates for the registry chemistries.

    Returns the matrix, the display names, how many conventional conjugates the registry
    holds, and the registry *keys* -- which are what the fitted agent list uses.
    """
    hit = _CACHE.get(id(post))
    if hit is not None and hit[0] is post:
        return hit[1], hit[2], hit[3], hit[4]
    mat, names, n_registry, keys = _compute_reference_matrix(post)
    _CACHE[id(post)] = (post, mat, names, n_registry, keys)
    return mat, names, n_registry, keys


def _compute_reference_matrix(post: Posterior) -> tuple[np.ndarray, list[str], int]:
    designs, n_conventional = _registry_designs()
    usable = [d for d in designs if d["mechanism"] in post.mechanisms]
    if not usable:
        return np.zeros((0, len(post.axes))), [], n_conventional, []
    draws = predict_draws(
        post,
        [d["mechanism"] for d in usable],
        [d["family"] for d in usable],
        np.array([d["dar"] for d in usable]),
        np.array([d["cleavable"] for d in usable], dtype=float),
        # Off deliberately: the comparison is between chemistries, and a per-agent residual
        # draw would make the ranking partly a function of the random seed.
        include_agent_variation=False,
    )
    return (
        draws.mean(axis=0),
        [d["inn"] for d in usable],
        n_conventional,
        [d["key"] for d in usable],
    )


def reference_count(post: Posterior) -> int:
    _, names, _, _ = _reference_matrix(post)
    return len(names)


def axis_comparator(post: Posterior, axis: str, rate: float) -> dict | None:
    """Ordinal position of `rate` among the corpus chemistries on one axis.

    `rank` is 1 for the highest rate, so rank 1 is the worst place to be. Returns None
    where the axis is unknown to the fit or no reference chemistry survives.
    """
    if axis not in post.axes:
        return None
    mat, names, n_registry, keys = _reference_matrix(post)
    if not names:
        return None
    col = mat[:, post.axes.index(axis)]
    # Strictly greater, so the queried design is not counted as beating a tie.
    higher = int((col > rate).sum())
    fitted = set(post.agents)
    return {
        "rank": higher + 1,
        "n": len(names) + 1,
        # Which event table, because a row can show a common-table point estimate beside a
        # comparator computed on the serious table -- the band follows the question asked
        # about the axis, and the comparator follows the band. Without this the two numbers
        # on one row look like they disagree.
        "table": post.kind,
        "n_reference_chemistries": len(names),
        # How many of the references the fit actually saw. None for a posterior written
        # before the agent list was recorded, which is not the same as zero.
        "n_reference_in_fitted_corpus": (
            sum(1 for k in keys if k in fitted) if fitted else None
        ),
        "n_excluded_for_missing_slots": n_registry - len(names),
        "interpretation": "relative_ranking_only",
        "basis": (
            "this model's prediction for the slots of every registry ADC with a fully "
            "stated chemistry, agent-level residual off; not their observed rates, which "
            "are censored at each trial's reporting cut"
        ),
    }
