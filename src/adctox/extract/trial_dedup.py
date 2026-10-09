"""Identify which trial a paper reports, and stop the same patients counting twice.

The risk showed up in the first eight articles fetched: four of them report NCT03589469,
the LOTIS-2 trial of loncastuximab tesirine. A fifth source for the same patients already
exists -- the ClinicalTrials.gov results record. Admitting all five would give that trial
five times its weight, and a trial random intercept cannot repair it: the duplicates are
the *same* arm with correlated counts, not independent observations that happen to share a
trial. The hierarchical model would read the agreement between them as precision.

Papers make the identification easy. 6 of 8 carry their NCT identifier in an `ext-link`,
and the id is also in the text, so recovery is deterministic rather than inferred.

Two decisions, kept separate because they are different questions.

**Which trial does this table report?** A paper with one NCT id answers it. A paper with
several does not: a review listing six trials, or a pooled analysis across three, cannot
have its tables assigned without reading them. Those are flagged, not guessed.

**Should this source be used?** That depends on what the corpus is for, so it is reported
rather than decided here. Every one of the 18 registry agents already has
ClinicalTrials.gov arms, which means this corpus adds no new agents -- it is a *validation*
set, where the overlap is the point: an extracted rate can be checked against the
registry's own number for the same arm. Corpus expansion needs the ~36 agents outside the
registry, and there the overlap is a duplicate to drop. Same data, opposite handling, so
`overlaps_registry` travels with each group and the caller chooses.

When duplicates do have to be collapsed, the choice is the largest denominator, tie-broken
by cell count and then by PMCID. Largest N is the fullest safety population, which is the
closest thing to the trial's complete record; determinism matters more than the tie-break
being clever, because a non-deterministic choice would make the corpus unreproducible.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

NCT = re.compile(r"NCT\d{8}")

# Sections whose trial ids are references to other people's trials, not this paper's.
# A discussion section naming six competitor trials would otherwise make every primary
# report look like a pooled analysis.
CITATION_CONTEXT = ("ref-list", "back")


def trial_ids(root) -> dict[str, list[str]]:
    """NCT ids in this article, grouped by where they were found.

    The location matters: an id in the reference list belongs to a cited trial, while an id
    in an `ext-link` or the article metadata belongs to this one.
    """
    found: dict[str, set[str]] = defaultdict(set)
    for el in root.findall(".//ext-link"):
        href = el.get("{http://www.w3.org/1999/xlink}href") or ""
        for m in NCT.findall(f"{href} {el.text or ''}"):
            ancestors = {a.tag for a in el.iterancestors() if isinstance(a.tag, str)}
            where = "citation" if ancestors & set(CITATION_CONTEXT) else "ext_link"
            found[where].add(m)
    for el in root.findall(".//article-id") + root.findall(".//related-object"):
        for m in NCT.findall("".join(el.itertext())):
            found["article_id"].add(m)
    body = root.find(".//body")
    if body is not None:
        for m in NCT.findall("".join(body.itertext())):
            found["body"].add(m)
    return {k: sorted(v) for k, v in found.items()}


def primary_trial(ids_by_location: dict[str, list[str]]) -> tuple[str | None, str]:
    """The one trial this paper reports, or None with a reason.

    Preference order follows how reliably a location names *this* paper's trial. An
    `ext-link` outside the reference list is the registration link journals require; the
    body is next; a reference-list id is somebody else's trial and never qualifies on its
    own.
    """
    for where in ("ext_link", "article_id", "body"):
        ids = ids_by_location.get(where) or []
        if len(ids) == 1:
            return ids[0], where
        if len(ids) > 1:
            return None, f"{where}_names_{len(ids)}_trials"
    return None, "no_trial_id"


@dataclass
class SourceGroup:
    """Every candidate source for one (trial, agent), and which one to use."""
    nct_id: str
    agent: str
    overlaps_registry: bool
    chosen_pmcid: str | None
    candidates: list[dict] = field(default_factory=list)
    reason: str = ""


def group_sources(
    sources: list[dict],
    registry_ncts: set[str],
) -> tuple[list[SourceGroup], list[dict]]:
    """Group paper sources by (trial, agent) and pick one per group.

    `sources` are dicts carrying at least `pmcid`, `agent`, `nct_id`, `max_denominator`
    and `n_cells`. Sources with no resolved trial are returned separately: they cannot be
    deduplicated, because there is no way to know whether they duplicate anything.
    """
    unresolved = [s for s in sources if not s.get("nct_id")]
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for s in sources:
        if s.get("nct_id"):
            by_key[(s["nct_id"], s["agent"])].append(s)

    groups: list[SourceGroup] = []
    for (nct, agent), cands in sorted(by_key.items()):
        best = max(
            cands,
            key=lambda s: (
                s.get("max_denominator") or 0,
                s.get("n_cells") or 0,
                # Negated so the smallest PMCID wins a full tie, making the choice stable
                # across runs and across the order the directory happened to list.
                -int(s["pmcid"]),
            ),
        )
        n_dup = len(cands) - 1
        groups.append(SourceGroup(
            nct_id=nct,
            agent=agent,
            overlaps_registry=nct in registry_ncts,
            chosen_pmcid=best["pmcid"],
            candidates=sorted(cands, key=lambda s: s["pmcid"]),
            reason=(
                f"largest denominator of {len(cands)} sources"
                if n_dup else "only source"
            ),
        ))
    return groups, unresolved
