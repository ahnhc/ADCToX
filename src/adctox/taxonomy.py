"""Organ-axis taxonomy: MedDRA SOC/PT strings -> the 14 organ axes.

Everything downstream depends on this module, so it is deliberately dependency-light
(PyYAML only) and has no knowledge of where the AE records came from.

Three jobs:

1. Normalize the raw ``organSystem`` strings ClinicalTrials.gov and the literature emit.
   Measured on 605 CTGov ADC studies: 50 distinct exact strings, which collapse to 28
   under casefold + whitespace normalization and to 27 once the ``general disorders``
   alias pair is merged. ALL-CAPS renderings are common enough to matter
   (``'INFECTIONS AND INFESTATIONS'``: 49 events).

2. Redistribute the ``Investigations`` SOC per preferred term. It is the 5th most common
   SOC (4,757 events, 617 PTs) and is pure organ signal under a lab-test label, so
   dropping it would delete the strongest haematologic and hepatic signals in the data.

3. Build and serve a PT -> SOC dictionary harvested from public-domain CTGov records,
   so the literature corpus (which reports PT only, no SOC) can be mapped to axes
   without a MedDRA licence.

On MedDRA: the dictionary is derived from public-domain FDA/CTGov records, but MedDRA
PT and SOC strings are themselves licensed terminology. The built dictionary therefore
stays local -- only the script that regenerates it is published. See docs/DATA_SOURCES.md.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml

CONF_DIR = Path(__file__).resolve().parents[2] / "conf" / "ontology"
AXES_YAML = CONF_DIR / "axes.yaml"
INVESTIGATIONS_YAML = CONF_DIR / "investigations_rules.yaml"

# Sentinel axis values. Callers must treat these as "not an observation", never as zero.
AXIS_UNMAPPED = "__unmapped__"
AXIS_EXCLUDED = "__excluded__"
AXIS_DROPPED = "__dropped__"

_SENTINELS = frozenset({AXIS_UNMAPPED, AXIS_EXCLUDED, AXIS_DROPPED})


def normalize_text(s: str | None) -> str:
    """Casefold, strip accents, collapse whitespace, and drop a trailing period.

    This is the single normalization used for both SOC and PT strings, so that
    ``'INFECTIONS AND INFESTATIONS'``, ``'Infections and infestations'`` and
    ``'Infections  and infestations '`` all collapse to one key.
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s).strip().casefold()
    return s.rstrip(".")


def parse_frequency_threshold(raw: object) -> float | None:
    """Parse CTGov's ``frequencyThreshold``, which is a *string* with mixed formats.

    Measured across 605 studies: ``'5'`` (402), ``'0'`` (182), ``'1'`` (8), ``'4'`` (3),
    ``'2'`` (3), ``'5.0'`` (2), ``'3'``, ``'4.9'``, ``'4.98'``, ``'5.00'``, and ``None``.
    Treating ``'5'`` and ``'5.0'`` as different values is a silent correctness bug, so
    every consumer must come through here.

    Returns the threshold as a percentage, or None when the field is absent. None means
    *unknown*, not zero -- an absent threshold must not be read as complete reporting.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().rstrip("%").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@dataclass(frozen=True)
class _InvestigationsRule:
    pattern: re.Pattern[str]
    axis: str
    source: str


class Taxonomy:
    """SOC/PT -> organ axis resolution, loaded from ``conf/ontology/``."""

    def __init__(
        self,
        axes_yaml: Path = AXES_YAML,
        investigations_yaml: Path = INVESTIGATIONS_YAML,
    ) -> None:
        axes_doc = yaml.safe_load(axes_yaml.read_text(encoding="utf-8"))
        inv_doc = yaml.safe_load(investigations_yaml.read_text(encoding="utf-8"))

        self.axes: dict[str, str] = {
            axis: spec["label"] for axis, spec in axes_doc["axes"].items()
        }
        self.axis_order: tuple[str, ...] = tuple(axes_doc["axes"])

        self._soc_to_axis: dict[str, str] = {}
        for axis, spec in axes_doc["axes"].items():
            for soc in spec["socs"]:
                self._soc_to_axis[normalize_text(soc)] = axis

        self._soc_aliases = {
            normalize_text(k): normalize_text(v)
            for k, v in (axes_doc.get("soc_aliases") or {}).items()
        }
        self._soc_redistribute = {
            normalize_text(s) for s in (axes_doc.get("soc_redistribute") or [])
        }
        self._soc_excluded = {
            normalize_text(k): v
            for k, v in (axes_doc.get("soc_excluded") or {}).items()
        }

        self._inv_rules = tuple(
            _InvestigationsRule(
                pattern=re.compile(rule["pattern"]),
                axis=rule["axis"],
                source=rule["pattern"],
            )
            for rule in inv_doc["rules"]
        )
        self._inv_drop = tuple(
            re.compile(p) for p in (inv_doc.get("drop_patterns") or [])
        )

        unknown = {r.axis for r in self._inv_rules} - set(self.axes)
        if unknown:
            raise ValueError(
                f"investigations_rules.yaml references unknown axes: {sorted(unknown)}"
            )

        # Guard against the YAML flow-sequence trap: several real SOC names contain a
        # comma ("Respiratory, thoracic and mediastinal disorders"), and an unquoted
        # `[a, b]` silently splits one name into two bogus entries. A split fragment is
        # always short, so a length floor catches it at load time instead of letting the
        # pulmonary axis quietly lose every event.
        suspicious = sorted(s for s in self._soc_to_axis if len(s) < 12)
        if suspicious:
            raise ValueError(
                "axes.yaml has SOC entries too short to be real MedDRA SOC names "
                f"{suspicious!r}; quote any value containing a comma"
            )

        # PT -> SOC dictionary, populated by load_pt_dictionary().
        self._pt_to_soc: dict[str, str] = {}

    # ------------------------------------------------------------------ SOC layer

    def canonical_soc(self, raw_soc: str | None) -> str:
        """Normalize a raw ``organSystem`` string to its canonical SOC key."""
        key = normalize_text(raw_soc)
        return self._soc_aliases.get(key, key)

    @property
    def canonical_socs(self) -> frozenset[str]:
        """Every SOC key this taxonomy knows: mapped, redistributed, or excluded."""
        return frozenset(
            set(self._soc_to_axis) | self._soc_redistribute | set(self._soc_excluded)
        )

    def soc_axis(self, raw_soc: str | None) -> str:
        """Axis for a SOC alone, without consulting the term.

        Returns ``AXIS_EXCLUDED`` for a deliberately excluded SOC and ``AXIS_UNMAPPED``
        for one we have never seen -- including ``Investigations``, which cannot be
        resolved without the term. Use :meth:`resolve` for the full path.
        """
        soc = self.canonical_soc(raw_soc)
        if soc in self._soc_to_axis:
            return self._soc_to_axis[soc]
        if soc in self._soc_excluded:
            return AXIS_EXCLUDED
        return AXIS_UNMAPPED

    # --------------------------------------------------- Investigations layer

    def redistribute_investigation(self, term: str | None) -> tuple[str, str | None]:
        """Resolve an ``Investigations`` term to an axis.

        Returns ``(axis_or_sentinel, matched_pattern)``. The first matching rule wins,
        so ordering in the YAML is load-bearing.
        """
        key = normalize_text(term)
        if not key:
            return AXIS_UNMAPPED, None
        for drop in self._inv_drop:
            if drop.search(key):
                return AXIS_DROPPED, drop.pattern
        for rule in self._inv_rules:
            if rule.pattern.search(key):
                return rule.axis, rule.source
        return AXIS_UNMAPPED, None

    # ------------------------------------------------------------ full resolution

    def _resolve_known_soc(self, term: str | None, soc: str) -> tuple[str, str] | None:
        """Resolve a SOC key the config already knows about, else None."""
        if soc in self._soc_redistribute:
            axis, pattern = self.redistribute_investigation(term)
            if axis in _SENTINELS:
                return axis, f"investigations:{axis}"
            return axis, f"investigations_rule:{pattern}"
        if soc in self._soc_to_axis:
            return self._soc_to_axis[soc], f"soc:{soc}"
        if soc in self._soc_excluded:
            return AXIS_EXCLUDED, f"soc_excluded:{self._soc_excluded[soc]}"
        return None

    def resolve(self, term: str | None, raw_soc: str | None) -> tuple[str, str]:
        """Map an AE record to an organ axis.

        Returns ``(axis_or_sentinel, provenance)`` where provenance names the route
        taken, so a downstream row can be audited without re-running the logic.

        The SOC gates the term: an ``Investigations`` rule can only fire on a term whose
        SOC *is* ``Investigations``. Without that gate, "Blood creatinine increased"
        filed under a real SOC would be stolen by the renal pattern.

        The PT-dictionary fallback is applied at most once. It cannot recurse: if the
        dictionary hands back a SOC the config still does not know, the record is
        unmapped rather than looked up again (an earlier version recursed until the
        stack blew).
        """
        soc = self.canonical_soc(raw_soc)

        direct = self._resolve_known_soc(term, soc)
        if direct is not None:
            return direct

        if self._pt_to_soc:
            inferred = self.canonical_soc(self._pt_to_soc.get(normalize_text(term)))
            if inferred and inferred != soc:
                via_dict = self._resolve_known_soc(term, inferred)
                if via_dict is not None:
                    axis, prov = via_dict
                    return axis, f"pt_dict->{prov}"

        return AXIS_UNMAPPED, f"unknown_soc:{soc or '<empty>'}"

    def resolve_term_only(self, term: str | None) -> tuple[str, str]:
        """Map a term with no SOC, as the literature corpus requires.

        Uses the harvested PT -> SOC dictionary, which must be loaded first.
        """
        if not self._pt_to_soc:
            raise RuntimeError(
                "PT dictionary not loaded; call load_pt_dictionary() first"
            )
        soc = self.canonical_soc(self._pt_to_soc.get(normalize_text(term)))
        if not soc:
            return AXIS_UNMAPPED, "pt_dict_miss"
        resolved = self._resolve_known_soc(term, soc)
        if resolved is None:
            return AXIS_UNMAPPED, f"pt_dict->unknown_soc:{soc}"
        axis, prov = resolved
        return axis, f"pt_dict->{prov}"

    # -------------------------------------------------------------- PT dictionary

    def load_pt_dictionary(self, path: Path) -> int:
        """Load a PT -> SOC dictionary written by :func:`build_pt_dictionary`."""
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        self._pt_to_soc = {
            normalize_text(term): entry["soc"]
            for term, entry in doc["terms"].items()
        }
        return len(self._pt_to_soc)

    @property
    def pt_dictionary_size(self) -> int:
        return len(self._pt_to_soc)


def build_pt_dictionary(
    records: Iterable[tuple[str, str]],
    min_majority: float = 0.5,
) -> dict:
    """Build a PT -> SOC dictionary from ``(term, raw_soc)`` pairs by majority vote.

    Measured on 605 CTGov ADC studies: 9,249 distinct terms, 7.6% assigned to more than
    one SOC and 4.6% genuinely contested (majority under 90%). The ambiguity is mostly
    the ``general disorders`` alias pair, which :meth:`Taxonomy.canonical_soc` already
    merges before voting.

    Returns a JSON-serializable document carrying, per term, the winning SOC, its
    vote share and the full vote counts -- so a contested term can be audited rather
    than silently resolved.
    """
    tax = Taxonomy()
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    display: dict[str, str] = {}

    for term, raw_soc in records:
        key = normalize_text(term)
        soc = tax.canonical_soc(raw_soc)
        if not key or not soc:
            continue
        votes[key][soc] += 1
        display.setdefault(key, (term or "").strip())

    terms: dict[str, dict] = {}
    contested = 0
    for key, counter in votes.items():
        total = sum(counter.values())
        soc, top = counter.most_common(1)[0]
        share = top / total
        if share < min_majority:
            continue
        if len(counter) > 1 and share < 0.9:
            contested += 1
        terms[display.get(key, key)] = {
            "soc": soc,
            "n": total,
            "majority_share": round(share, 4),
            "votes": dict(counter),
        }

    return {
        "terms": terms,
        "stats": {
            "distinct_terms": len(votes),
            "retained_terms": len(terms),
            "multi_soc_terms": sum(1 for c in votes.values() if len(c) > 1),
            "contested_terms": contested,
            "total_observations": sum(sum(c.values()) for c in votes.values()),
        },
    }


@lru_cache(maxsize=1)
def default_taxonomy() -> Taxonomy:
    """Process-wide Taxonomy built from the checked-in config.

    Construction costs about 20ms, and the request paths were paying it per call -- this
    singleton existed to stop that and nothing used it.

    Use it only where the instance stays read-only. `load_pt_dictionary` mutates the
    object, so the corpus-build scripts construct their own; sharing one with them would
    hand a mutated dictionary to every later caller. Everything that only reads `axes`,
    `axis_order` or resolves a known SOC can share this one.
    """
    return Taxonomy()
