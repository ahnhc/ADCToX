"""Parse dose-modification tables into an ordinal organ-severity ranking per drug.

What this measures: every approved label's section 2 states, per adverse reaction and
grade, whether to monitor, reduce, withhold or permanently discontinue. That is the
clinical community's operational judgement about which organs it fears for that drug, and
the four actions carry a natural ordering. Comparing the model's 14-axis ranking against
it gives roughly a hundred ordered pairs across 14 drugs with an ordinal outcome, against
the 7 binary events the label-change analysis offers.

Parsing notes, all forced by the real markup rather than chosen:

* A reaction name often appears once in a header-like row, with the grades and actions on
  the rows beneath it, so the last-seen reaction label has to be carried forward.
* The same reaction appears at several grades with escalating actions, so the per-axis
  value is the strongest action anywhere for that organ.
* Captions and abbreviation footer rows look like data rows and must be skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import html

# Ordinal severity of the instruction. Higher means the label is more afraid of it.
ACTION_ORDINAL: list[tuple[str, int, str]] = [
    # Deliberately narrow. A bare `\bdiscontinue\b` also matches "Discontinue
    # vincristine", which is an instruction about the *combination partner*, and matched
    # so widely that every axis collapsed to the top of the scale.
    (r"permanently discontinue|discontinue (treatment|permanently)|"
     r"discontinue (ADCETRIS|ENHERTU|PADCEV|TRODELVY|KADCYLA|POLIVY|TIVDAK|ELAHERE|"
     r"BESPONSA|MYLOTARG|ZYNLONTA|DATROWAY|EMRELIS|DECNUPAZ)", 4,
     "permanently_discontinue"),
    (r"withhold|interrupt|\bhold\b|omit|delay", 3, "withhold"),
    (r"reduce (the )?dose|dose reduction|decrease (the )?dose", 2, "reduce_dose"),
    (r"monitor|continue .* at (the )?current dose|no dose (modification|adjustment)",
     1, "monitor"),
]

# Reaction label -> organ axis. Reused deliberately from the label-change mapping's
# vocabulary so the two Module B analyses speak about the same axes.
REACTION_TO_AXIS: list[tuple[str, str]] = [
    (r"interstitial lung|pneumonitis|pulmonary|respiratory|dyspn", "pulmonary"),
    (r"hepatotox|hepatic|veno-?occlusive|\bvod\b|bilirubin|\balt\b|\bast\b|"
     r"transaminase|liver", "hepatic"),
    (r"neutropeni|thrombocytopeni|an(a)?emia|leukopeni|lymphopeni|myelosuppress|"
     r"h(a)?ematologic|cytopeni|platelet|neutrophil|bone marrow|febrile", "haematologic"),
    (r"peripheral neuropath|neuropath|neurotox|neurologic|"
     r"progressive multifocal|leukoencephalopath", "neurologic"),
    (r"ocular|keratopath|keratitis|corneal|\beye\b|visual|blurred vision|"
     r"dry eye", "ocular"),
    (r"left ventricular|ejection fraction|cardiomyopath|cardiac|qt",
     "cardiovascular"),
    (r"h(a)?emorrhage|bleeding|thrombo|capillary leak|effusion|\bedema\b|"
     r"hypotension|hypertension", "cardiovascular"),
    (r"renal|nephrotox|creatinine|kidney|proteinuria", "renal"),
    (r"diarrh|colitis|nausea|vomit|stomatitis|mucositis|pancreatitis|"
     r"gastrointestinal|bowel|lipase|amylase", "gastrointestinal"),
    (r"skin reaction|cutaneous|dermatolog|rash|stevens-?johnson|"
     r"toxic epidermal|\bsjs\b|\bten\b|alopecia|palmar", "dermatologic"),
    (r"hyperglyc|hypoglyc|tumor lysis|electrolyte|hypokal|hypomagnes|"
     r"hypocalc|thyroid|metabol", "metabolic_endocrine"),
    (r"infection|sepsis|opportunistic|hepatitis b reactivat|neutropenic fever",
     "infectious_immune"),
    (r"infusion[- ]?(related )?reaction|hypersensitivity|anaphyla|"
     r"cytokine release", "infectious_immune"),
    (r"ototox|hearing", "otologic"),
    (r"fatigue|asthenia|pyrexia|fever|weight", "constitutional"),
]

# Rows that look like data but are not: captions, abbreviation keys, dose-escalation
# schedules keyed by occurrence rather than by reaction.
_SKIP_ROW = re.compile(
    r"^abbreviation|^table \d|^footnote|^\*|"
    r"^(first|second|third|fourth)\b.*(dose )?reduction|"
    r"^recommended (starting )?dose|^dose reduction schedule|"
    r"^requirement for further",
    re.IGNORECASE,
)
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def axis_for_reaction(label: str) -> str | None:
    text = _clean(label).lower()
    if not text or _SKIP_ROW.match(text):
        return None
    for pattern, axis in REACTION_TO_AXIS:
        if re.search(pattern, text):
            return axis
    return None


def action_ordinal(text: str) -> tuple[int, str] | None:
    """Strongest instruction in a cell. Several can co-occur in one cell, so the maximum
    wins -- "withhold until Grade 1, then permanently discontinue if it recurs" is a
    discontinue instruction."""
    low = _clean(text).lower()
    best: tuple[int, str] | None = None
    for pattern, rank, name in ACTION_ORDINAL:
        if re.search(pattern, low) and (best is None or rank > best[0]):
            best = (rank, name)
    return best


# Toxicity grade mentioned in a row, when there is one.
_GRADE = re.compile(r"grade\s*([1-5])", re.IGNORECASE)
_GRADE_OR_GREATER = re.compile(r"grade\s*([1-5])\s*(or (greater|higher)|\+|and above)",
                               re.IGNORECASE)


def row_grade(cells: list[str]) -> int | None:
    """Lowest CTCAE grade named in a row, or None.

    The lowest is taken because a row reading "Grade 2 or greater" is triggered at grade 2.
    """
    grades: list[int] = []
    for cell in cells:
        for m in _GRADE.finditer(cell):
            grades.append(int(m.group(1)))
    return min(grades) if grades else None


@dataclass
class DoseModEntry:
    agent: str
    axis: str
    reaction: str
    severity: int
    action: str
    grade: int | None
    source_table: int


def parse_tables(agent: str, tables: list[str]) -> list[DoseModEntry]:
    """Extract (axis, strongest action) entries from a label's dose-modification tables."""
    out: list[DoseModEntry] = []
    for ti, raw in enumerate(tables):
        try:
            doc = html.fromstring(raw)
        except Exception:
            continue
        caption = _clean(
            doc.xpath("//caption")[0].text_content() if doc.xpath("//caption") else ""
        )
        # Only tables keyed by adverse reaction are relevant; a "Recommended Dosage"
        # table lists indications, not toxicities.
        if not re.search(r"modificat|adverse|toxicit|management", caption, re.I):
            continue

        current_axis: str | None = None
        current_reaction = ""
        for tr in doc.xpath("//tr"):
            cells = [_clean(c.text_content()) for c in tr.xpath("./td|./th")]
            if not cells or all(not c for c in cells):
                continue
            if _SKIP_ROW.match(cells[0]):
                continue
            # A reaction name in the first cell updates the running context; rows that
            # only carry a grade and an action inherit it.
            axis = axis_for_reaction(cells[0])
            if axis is not None:
                current_axis, current_reaction = axis, cells[0]
            if current_axis is None:
                continue
            for cell in cells:
                hit = action_ordinal(cell)
                if hit is None:
                    continue
                severity, action = hit
                out.append(
                    DoseModEntry(
                        agent=agent, axis=current_axis,
                        reaction=current_reaction[:80], severity=severity,
                        action=action, grade=row_grade(cells), source_table=ti,
                    )
                )
    return out


def axis_severity(entries: list[DoseModEntry]) -> dict[str, int]:
    """Strongest instruction per organ axis.

    Kept for reference, but it is a poor discriminator: approved labels tell you to
    discontinue for the severe grade of nearly every reaction, so almost every axis
    collapses to the top of the scale. Use `axis_concern` instead.
    """
    out: dict[str, int] = {}
    for e in entries:
        out[e.axis] = max(out.get(e.axis, 0), e.severity)
    return out


def axis_concern(entries: list[DoseModEntry]) -> dict[str, float]:
    """A graded measure of how much the label fears each organ.

    The discriminating quantity is not *whether* a label says to stop, since it says that
    for the severe grade of nearly everything, but **at what grade it starts to act**. A
    drug to be withheld at grade 1 is feared more than one withheld only at grade 3.

    Score = strongest action (1-4) plus a bonus for how early it is triggered, so the
    scale stays ordinal and interpretable: 4.8 means "discontinue, and from grade 1".
    Rows with no grade contribute the action alone.
    """
    best: dict[str, tuple[int, int | None]] = {}
    for e in entries:
        if e.severity < 3:  # only withhold and discontinue express real fear
            continue
        cur = best.get(e.axis)
        if cur is None or (e.severity, -(e.grade or 9)) > (cur[0], -(cur[1] or 9)):
            best[e.axis] = (e.severity, e.grade)
    out: dict[str, float] = {}
    for axis, (severity, grade) in best.items():
        early = 0.0 if grade is None else (5 - grade) * 0.2
        out[axis] = severity + early
    # Axes mentioned only with a monitoring instruction still register, below the rest.
    for e in entries:
        if e.axis not in out:
            out[e.axis] = float(e.severity)
    return out
