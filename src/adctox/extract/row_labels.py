"""Classify a paper table's row label, and map it to an organ axis.

Papers give preferred terms without a system organ class. The corpus already carries the
missing half: a PT -> SOC dictionary harvested from ClinicalTrials.gov, where public-domain
records carry `term` and `organSystem` together -- 7,068 terms over 67,607 observations,
each with the share of observations backing its majority SOC. So the mapping is a dictionary
lookup, and this module is about the labels that miss it.

The plan measured the miss rate on 717 real paper row labels: exact 41.6%, fuzzy 8.9%,
unmapped 49.5%. It then decomposed the unmapped half, and that decomposition is why this
module has the shape it does:

* **60% are aggregate rows** -- "Any treatment-emergent adverse event", "Overall",
  "Any grade >=3 event". These are not organ rows and must be dropped, not mapped. They are
  also the most dangerous rows in the table, because they carry the largest counts: a
  single aggregate row misread as an organ row would put a 95% rate on whatever axis it
  landed on, outweighing every real row in that table.
* **3% are SOC headers**, usable directly.
* **23% are recoverable by rule**, and the rules are clerical rather than clinical. Papers
  write "Increased ALT" where MedDRA writes "Alanine aminotransferase increased": adjective
  first instead of last, and abbreviated. British spelling accounts for much of the rest --
  the dictionary is American because ClinicalTrials.gov is.
* **13% are a genuine residual**, left unmapped rather than guessed.

Nothing here does clinical inference. Every rule is a spelling, an abbreviation, a word
order or a footnote marker, so a rule firing wrongly produces a dictionary miss rather
than a wrong organ -- the failure is silent only in the direction of losing data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..taxonomy import AXIS_UNMAPPED, Taxonomy, normalize_text

# A row whose label names no specific event. Dropped: these carry the table's largest
# counts and would dominate whatever axis they were assigned to.
AGGREGATE = re.compile(
    r"^\s*(?:"
    r"(?:the\s+)?(?:number|proportion|incidence)\s+of\s+patients"
    r"|(?:any|all|overall|total|at\s+least\s+one|[>≥]\s*1)\b"
    r"|patients?\s+with\b"
    r"|(?:treatment[-\s](?:emergent|related)|drug[-\s]related)\s+"
    r"(?:adverse\s+events?|aes?|teaes?)\b"
    r"|(?:serious|severe|grade\s*[≥>=]*\s*[1-5])\s+"
    r"(?:adverse\s+events?|aes?|teaes?)\b"
    r"|adverse\s+events?\b|aes?\b|teaes?\b|traes?\b"
    r"|(?:any\s+)?(?:event|toxicit(?:y|ies))\s+(?:leading|resulting)\s+to\b"
    r"|(?:dose\s+(?:reduction|interruption|delay|modification)"
    r"|(?:treatment\s+)?discontinuation|death|withdrawal)s?\b"
    r")",
    re.I,
)
# ... and the same idea stated as a suffix, which the prefix pattern cannot see:
# "Adverse events leading to dose reduction", "TEAEs of special interest".
AGGREGATE_TAIL = re.compile(
    r"\b(?:leading\s+to|resulting\s+in|of\s+special\s+interest|of\s+any\s+grade"
    r"|requiring\s+(?:dose|treatment)|causing\s+(?:death|discontinuation))\b",
    re.I,
)

# Footnote markers, trailing punctuation, and the grade qualifiers papers append to a
# term. "Nausea, any grade" and "Nausea" are the same row label.
FOOTNOTE = re.compile(r"[†‡§¶*#®™]+|\s*\(\s*[a-z]\s*\)\s*$")
SUPERSCRIPT_DIGIT = re.compile(r"[¹²³⁰-⁹]+")
GRADE_QUALIFIER = re.compile(
    r"[,;(–—-]\s*(?:any[-\s]grade|all[-\s]grades?"
    r"|grade\s*[≥>=]*\s*[1-5](?:\s*[-–]\s*[1-5])?"
    r"|n\s*\(\s*%\s*\))\s*\)?\s*$",
    re.I,
)
TRAILING_PUNCT = re.compile(r"[\s,;:.]+$")

# Papers write the modifier first; MedDRA writes it last. The dictionary is American
# because ClinicalTrials.gov is.
MODIFIER_FIRST = re.compile(
    r"^(increased|decreased|elevated|reduced|raised|low|high|abnormal|prolonged)\s+"
    r"(.+)$",
    re.I,
)
MODIFIER_CANONICAL = {
    "increased": "increased", "elevated": "increased", "raised": "increased",
    "high": "increased", "decreased": "decreased", "reduced": "decreased",
    "low": "decreased", "abnormal": "abnormal", "prolonged": "prolonged",
}

# Laboratory abbreviations, expanded to the dictionary's spelling. Every entry here is a
# clerical expansion of an abbreviation in standard use, not a clinical judgement.
ABBREVIATIONS = {
    "alt": "alanine aminotransferase",
    "sgpt": "alanine aminotransferase",
    "ast": "aspartate aminotransferase",
    "sgot": "aspartate aminotransferase",
    "alp": "blood alkaline phosphatase",
    "alkaline phosphatase": "blood alkaline phosphatase",
    "ggt": "gamma-glutamyltransferase",
    "ldh": "blood lactate dehydrogenase",
    "cpk": "blood creatine phosphokinase",
    "ck": "blood creatine phosphokinase",
    "anc": "neutrophil count",
    "wbc": "white blood cell count",
    "rbc": "red blood cell count",
    "hb": "haemoglobin",
    "hgb": "haemoglobin",
    "plt": "platelet count",
    "creatinine": "blood creatinine",
    "bilirubin": "blood bilirubin",
    "total bilirubin": "blood bilirubin",
    "ldl": "low density lipoprotein",
    "lvef": "ejection fraction",
}

# British to American, which is the direction the dictionary needs.
SPELLING = [
    (re.compile(r"\bdiarrhoea\b", re.I), "diarrhea"),
    (re.compile(r"\ban(a)?emia\b", re.I), "anemia"),
    (re.compile(r"\bana?emic\b", re.I), "anemic"),
    (re.compile(r"\boedema\b", re.I), "edema"),
    (re.compile(r"\bhaemo", re.I), "hemo"),
    (re.compile(r"\bhaema", re.I), "hema"),
    (re.compile(r"\bleuco", re.I), "leuko"),
    (re.compile(r"\bdyspnoea\b", re.I), "dyspnea"),
    (re.compile(r"\bpyrexia\b", re.I), "pyrexia"),
    (re.compile(r"\btumour", re.I), "tumor"),
    (re.compile(r"\boesophag", re.I), "esophag"),
    (re.compile(r"\bcoagulopathy\b", re.I), "coagulopathy"),
    (re.compile(r"\bparaesthesia\b", re.I), "paresthesia"),
    # The British "ae" digraph, in the two medical suffixes where it survives.
    (re.compile(r"paenia\b", re.I), "penia"),
    (re.compile(r"aemia\b", re.I), "emia"),
    (re.compile(r"\banaesthe", re.I), "anesthe"),
    (re.compile(r"\bpaediatric", re.I), "pediatric"),
]


@dataclass(frozen=True)
class MappedRow:
    label: str                 # the label as printed
    kind: str                  # 'pt' | 'aggregate' | 'soc_header' | 'other'
    axis: str                  # an axis id, or AXIS_UNMAPPED
    provenance: str            # which step resolved it, for the audit ledger
    normalized: str = ""       # the string actually looked up, when one was


def strip_decoration(label: str) -> str:
    """Remove footnote markers and grade qualifiers, leaving the term itself."""
    s = SUPERSCRIPT_DIGIT.sub("", label)
    s = FOOTNOTE.sub("", s)
    # A grade qualifier can be followed by a footnote and vice versa, so alternate until
    # the string stops changing rather than assuming an order.
    for _ in range(3):
        before = s
        s = GRADE_QUALIFIER.sub("", s)
        s = FOOTNOTE.sub("", s)
        s = TRAILING_PUNCT.sub("", s)
        if s == before:
            break
    return re.sub(r"\s+", " ", s).strip()


def _spelling(s: str) -> str:
    for pat, repl in SPELLING:
        s = pat.sub(repl, s)
    return s


def rewrite_candidates(label: str) -> list[str]:
    """Every spelling of this label worth looking up, most faithful first.

    Ordered so that a label the dictionary already knows is never rewritten: an exact hit
    on the printed term is always preferred to a rule-derived one.
    """
    base = strip_decoration(label)
    out: list[str] = [base]

    def add(s: str) -> None:
        s = re.sub(r"\s+", " ", s).strip()
        if s and s.lower() not in {o.lower() for o in out}:
            out.append(s)

    add(_spelling(base))

    # "Increased ALT" -> "ALT increased" -> "Alanine aminotransferase increased".
    for variant in list(out):
        m = MODIFIER_FIRST.match(variant)
        if m:
            modifier = MODIFIER_CANONICAL[m.group(1).lower()]
            add(f"{m.group(2)} {modifier}")

    # Abbreviation expansion, applied to every variant produced so far. The longest
    # abbreviation wins, so "total bilirubin" is not expanded as "bilirubin".
    for variant in list(out):
        low = variant.lower()
        for abbr in sorted(ABBREVIATIONS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(abbr)}\b", low):
                add(re.sub(rf"\b{re.escape(abbr)}\b", ABBREVIATIONS[abbr], low,
                           flags=re.I))
                break
    for variant in list(out):
        add(_spelling(variant))
    return out


def classify(label: str) -> str:
    """'aggregate' | 'soc_header' | 'pt' | 'other', from the label text alone."""
    stripped = strip_decoration(label)
    if not stripped:
        return "other"
    if AGGREGATE.match(stripped) or AGGREGATE_TAIL.search(stripped):
        return "aggregate"
    return "pt"


def map_row(label: str, taxonomy: Taxonomy) -> MappedRow:
    """Resolve one printed row label to an organ axis, or decline to."""
    stripped = strip_decoration(label)
    if not stripped:
        return MappedRow(label, "other", AXIS_UNMAPPED, "empty_label")

    # A SOC header is checked before the aggregate pattern, because several canonical SOC
    # names begin with a word the aggregate pattern claims -- "General disorders and
    # administration site conditions" is a usable header, not an aggregate row.
    canon = taxonomy.canonical_soc(stripped)
    if canon in taxonomy.canonical_socs:
        axis = taxonomy.soc_axis(stripped)
        return MappedRow(label, "soc_header", axis, "soc_header", normalize_text(canon))

    if classify(stripped) == "aggregate":
        return MappedRow(label, "aggregate", AXIS_UNMAPPED, "aggregate_row", stripped)

    for i, cand in enumerate(rewrite_candidates(label)):
        axis, prov = taxonomy.resolve_term_only(cand)
        if axis != AXIS_UNMAPPED:
            step = "verbatim" if i == 0 else f"rewrite[{i}]"
            return MappedRow(label, "pt", axis, f"{step}:{prov}", cand)

    return MappedRow(label, "pt", AXIS_UNMAPPED, "pt_dict_miss", stripped)
