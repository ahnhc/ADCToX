"""Detect dated additions of organ-system warnings to approved ADC labels.

This is the only genuinely anticipatory target in the public record. Everything else the
project measures -- exclusion-criteria enrichment, mechanism fingerprints -- agrees with
warnings that already existed when the drug was approved, which is consistency rather
than prediction. A warning FDA *added* years after approval gives a date: before it, the
organ was not flagged; after it, it was. A model fit only on data predating that date
either ranked the organ highly or it did not.

Three things this module is careful about, each learned from the data:

* **Rename versus addition.** "Neutropenia" becoming "Hematologic Toxicities" is a
  rewording, not a new organ. Candidate events are emitted with the surrounding context
  so they can be adjudicated by hand; roughly thirty diffs across the corpus need it.
* **Severity escalation versus a new axis.** A warning moving from section 5 into the
  boxed warning is a change in emphasis on an organ already flagged. Tracked separately.
* **Granularity is the axis, not the heading.** A second warning on an organ already
  flagged -- trastuzumab emtansine gaining "Hemorrhage" when "Left Ventricular
  Dysfunction" already put it on the cardiovascular axis -- is not counted. That is the
  right target for a model that predicts per-axis risk: the question is whether it ranked
  an organ that had not yet been flagged at all. Heading-level counting yields more
  events but some of them are not predictions the model could be scored on.
* **Local reactions are not organ systems.** "Infusion Site Extravasation Injury" is a
  site reaction and is excluded, as is anything that maps to no organ axis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lxml import html

# Maps a section-5 subsection heading to an organ axis. Generous by design: a heading that
# matches nothing is reported as unmapped rather than silently dropped, because a missed
# mapping would hide a real event.
HEADING_TO_AXIS: list[tuple[str, str]] = [
    (r"interstitial lung|pneumonitis|pulmonary tox|respiratory", "pulmonary"),
    (r"hepatotox|hepatic|veno-?occlusive|sinusoidal obstruction|liver", "hepatic"),
    (r"neutropeni|thrombocytopeni|anemia|anaemia|myelosuppress|h(a)?ematologic|"
     r"cytopeni|leukopeni|bone marrow", "haematologic"),
    (r"peripheral neuropath|neurotox|neurologic|progressive multifocal|"
     r"leukoencephalopath|demyelinat", "neurologic"),
    (r"ocular|keratopath|corneal|eye|visual|blurred vision", "ocular"),
    (r"cardiomyopath|cardiac|left ventricular|ejection fraction|"
     # "QT Interval Prolongation" appears 20 times across the corpus and was unmapped
     # until the words were allowed to be separated.
     r"qt\s+(interval\s+)?prolong", "cardiovascular"),
    (r"h(a)?emorrhage|bleeding|thrombo(sis|embol)|capillary leak|hypotension|"
     # "Effusion and Edema" (12 occurrences) is a fluid-distribution warning and belongs
     # on the vascular axis.
     r"vascular|effusion|\bedema\b", "cardiovascular"),
    (r"renal|nephrotox|kidney", "renal"),
    (r"gastrointestinal|diarrh|colitis|pancreatitis|bowel|stomatitis|mucositis|"
     r"nausea|vomiting", "gastrointestinal"),
    (r"dermatolog|cutaneous|skin|stevens-?johnson|toxic epidermal|rash|alopecia", "dermatologic"),
    (r"hyperglyc|hypoglyc|diabet|endocrine|metabol|tumor lysis|thyroid|"
     # Reduced UGT1A1 activity is a metabolising-capacity warning, not an organ lesion,
     # but it governs systemic exposure and is reported on the metabolic axis.
     r"ugt1a", "metabolic_endocrine"),
    (r"infection|opportunistic|sepsis|immunosuppress|hepatitis b|progressive.*"
     r"infect", "infectious_immune"),
    (r"ototox|hearing|audi", "otologic"),
    # "Infusion Reactions" without the word "related" occurs 6 times.
    (r"infusion[- ]?(related\s+)?reaction|hypersensitivity|anaphyla|"
     r"sulfite allergic", "infectious_immune"),
    (r"fatigue|pyrexia|fever|asthenia|constitutional", "constitutional"),
]

# Headings that are real label sections but not organ-system warnings. Excluded explicitly
# so they do not show up as unmapped noise.
NOT_AN_ORGAN = re.compile(
    r"embryo|fetal|pregnan|lactation|immunization|vaccin|"
    r"extravasation|injection site|infusion site|"
    r"laboratory test|drug interaction|overdos|"
    r"increased mortality|second primary|secondary malignan|"
    # Companion-diagnostic and patient-selection sections, not toxicity.
    r"her2 testing|biomarker|patient selection|"
    # Population and indication caveats rather than an organ warning.
    r"adverse-?risk cytogenetic|non-?relapse mortality|post-?transplant",
    re.IGNORECASE,
)

_SEC5 = re.compile(r"^\s*5\.(\d+)\s+(.*)$")
_SEC5_TITLE = re.compile(r"^\s*WARNINGS?\s+AND\s+PRECAUTIONS\b", re.IGNORECASE)
_WS = re.compile(r"\s+")


def axis_for_heading(heading: str) -> str | None:
    """Organ axis for a section-5 heading, or None if it is not an organ warning."""
    text = _WS.sub(" ", heading).strip().lower()
    if NOT_AN_ORGAN.search(text):
        return None
    for pattern, axis in HEADING_TO_AXIS:
        if re.search(pattern, text):
            return axis
    return None


def axes_for_heading(heading: str) -> list[str]:
    """Every organ axis a heading names, in table order.

    ``axis_for_heading`` keeps the first match because the label-change diff counts one
    axis per heading; a scorer that needs every organ a warning touches uses this.
    """
    text = _WS.sub(" ", heading).strip().lower()
    if NOT_AN_ORGAN.search(text):
        return []
    out: list[str] = []
    for pattern, axis in HEADING_TO_AXIS:
        if axis not in out and re.search(pattern, text):
            out.append(axis)
    return out


@dataclass
class LabelVersion:
    agent: str
    version: int
    date: str | None
    boxed_headline: str | None
    sec5: dict[str, str]           # "5.1" -> heading text
    axes: dict[str, list[str]]     # axis -> headings that mapped to it
    unmapped: list[str]
    boxed_axes: list[str]


def parse_version(path: Path, agent: str, version: int, date: str | None) -> LabelVersion:
    doc = html.parse(str(path)).getroot()

    boxed = None
    for h1 in doc.xpath("//h1"):
        text = _WS.sub(" ", h1.text_content()).strip()
        # "WARNINGS AND PRECAUTIONS" is section 5's own heading, not a boxed warning; labels
        # without a box (datopotamab, loncastuximab, ...) put it in an <h1> too.
        if text.upper().startswith("WARNING") and not _SEC5_TITLE.match(text):
            boxed = text
            break

    sec5: dict[str, str] = {}
    for h2 in doc.xpath("//h2"):
        text = _WS.sub(" ", h2.text_content()).strip()
        m = _SEC5.match(text)
        if m:
            sec5[f"5.{m.group(1)}"] = m.group(2).strip()

    axes: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for heading in sec5.values():
        axis = axis_for_heading(heading)
        if axis is None:
            if not NOT_AN_ORGAN.search(heading.lower()):
                unmapped.append(heading)
            continue
        axes.setdefault(axis, []).append(heading)

    boxed_axes: list[str] = []
    if boxed:
        # A boxed warning headline can name several organs at once, e.g.
        # "INTERSTITIAL LUNG DISEASE and EMBRYO-FETAL TOXICITY".
        # Case-insensitive: boxed headlines are upper case ("NEUTROPENIA AND DIARRHEA"), and a
        # case-sensitive split read that headline as neutropenia alone.
        for part in re.split(r"\band\b|,|;", boxed[len("WARNING"):].lstrip(": "), flags=re.IGNORECASE):
            axis = axis_for_heading(part)
            if axis and axis not in boxed_axes:
                boxed_axes.append(axis)

    return LabelVersion(
        agent=agent, version=version, date=date, boxed_headline=boxed,
        sec5=sec5, axes=axes, unmapped=unmapped, boxed_axes=boxed_axes,
    )


@dataclass
class AxisEvent:
    agent: str
    axis: str
    kind: str               # 'axis_added' | 'escalated_to_boxed'
    from_version: int
    to_version: int
    date: str | None
    heading: str
    prior_headings: list[str]   # section-5 headings in the previous version, for adjudication
    needs_adjudication: bool
    adjudication_reason: str | None


# Labels whose version history spans a market withdrawal and a later re-approval. A diff
# across that boundary compares two different regulatory submissions, so a section present
# in the re-approved label is not an addition to a continuously marketed one.
# Gemtuzumab ozogamicin was withdrawn in 2010 and re-approved on 2017-09-01, and the
# naive diff produced three spurious "additions" dated 2017-09-13.
WITHDRAWAL_BOUNDARIES: dict[str, str] = {
    "gemtuzumab_ozogamicin": "2017-09-01",
}


def _is_across_withdrawal(agent: str, prev_date: str | None, cur_date: str | None) -> bool:
    boundary = WITHDRAWAL_BOUNDARIES.get(agent)
    if not boundary or not prev_date or not cur_date:
        return False
    from datetime import datetime

    def _parse(s: str):
        for fmt in ("%b %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s.strip(), fmt)
            except ValueError:
                continue
        return None

    b = _parse(boundary)
    p, c = _parse(prev_date), _parse(cur_date)
    return bool(b and p and c and p < b <= c)


def diff_versions(versions: list[LabelVersion]) -> list[AxisEvent]:
    """Find axes that appear in a version and not its predecessor.

    A candidate is marked for hand adjudication when the previous version had an unmapped
    heading, because a rename out of an unrecognized wording looks identical to a genuine
    addition from this vantage point.
    """
    ordered = sorted(versions, key=lambda v: v.version)
    events: list[AxisEvent] = []
    for prev, cur in zip(ordered, ordered[1:]):
        if _is_across_withdrawal(cur.agent, prev.date, cur.date):
            continue
        for axis, headings in cur.axes.items():
            if axis in prev.axes:
                continue
            reason = None
            if prev.unmapped:
                reason = (
                    "the previous version had unrecognized section-5 headings "
                    f"({'; '.join(prev.unmapped[:3])}), so this may be a rename"
                )
            events.append(
                AxisEvent(
                    agent=cur.agent, axis=axis, kind="axis_added",
                    from_version=prev.version, to_version=cur.version, date=cur.date,
                    heading=headings[0], prior_headings=sorted(prev.sec5.values()),
                    needs_adjudication=reason is not None, adjudication_reason=reason,
                )
            )
        for axis in cur.boxed_axes:
            if axis not in prev.boxed_axes:
                events.append(
                    AxisEvent(
                        agent=cur.agent, axis=axis, kind="escalated_to_boxed",
                        from_version=prev.version, to_version=cur.version, date=cur.date,
                        heading=cur.boxed_headline or "", prior_headings=[],
                        needs_adjudication=False, adjudication_reason=None,
                    )
                )
    return events
