"""MONDO's numbered gene-locus subtypes ('hypertrophic cardiomyopathy 3') and the general concept each one belongs to.

A patient with a common disease should not read as a rare genetic subtype nobody typed. general_map() is the one table behind that:
{subtype id: [subtype name, general id or None, general name or None]} (data/curated/disease_linking/subtype_general.json, written
by ml/build_subtypes.py from the MONDO file; the app build embeds it). keeps() says when the typed text itself names the subtype."""
import json, os, re

ROMAN = {"ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13}
_NUM = r"\d+[a-z]?\d?[a-z]?(?:/[a-z])?"
_ROM = "|".join(sorted(ROMAN, key=len, reverse=True)) + "|i"
_NAME = re.compile(rf"^(?P<stem>.+?)(?:,\s*|\s+)(?:(?P<word>(?:sub)?type\s+(?:type\s+)?|complementation group\s+))?"
                   rf"(?P<num>{_NUM}|(?<=type )[a-z]\d+|{_ROM})(?:,\s.*|\s+multiple types)?$", re.I)
# a number that is not a locus: the chromosome, the factor, the stage and the virus are the disease's own name
_NOT_LOCUS = re.compile(r"\b(?:chromosome|trisomy|monosomy|disomy|tetrasomy|pentasomy|triploidy|factors?|stage|grade|class|group|locus)$|virus|herpes", re.I)
_NAMED = re.compile(r"\d|\b(?:sub)?type\b|타입|\b(?:" + "|".join(ROMAN) + r")\b", re.I)
_WORD = re.compile(r"[a-z]+", re.I)

_MAP = {}


def general_map():
    if not _MAP:
        try:
            from __adc_data__ import _portable_data
            _MAP.update(_portable_data().get("subtypes", {}))
        except ImportError:
            try: _MAP.update(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "disease_linking", "subtype_general.json"), encoding="utf-8")))
            except OSError: pass
    return _MAP


def parse(name):
    """-> (stem, number) of a numbered subtype's name ('Stickler syndrome, type 5' -> ('Stickler syndrome', '5')), else None.
    'type 2 diabetes mellitus', 'COVID-19', 'factor V deficiency' and 'trisomy 21' are not."""
    m = _NAME.match(name.strip())
    if not m or _NOT_LOCUS.search(m["stem"].strip(" ,")) or (m["num"] == "46" and not name.strip().endswith("46")): return None     # "46, XY ...": a karyotype
    if not m["word"] and m["num"].lower() in ROMAN.keys() | {"i"} and not m["num"].isupper(): return None     # a Roman numeral only when written as one
    return m["stem"].strip(" ,"), m["num"]


def names_number(text):
    """the typed text contains a digit, a Roman numeral, or the word type or subtype."""
    return bool(_NAMED.search(text))


def _canon(token):
    token = token.lower()
    return str(ROMAN.get(token, 1 if token == "i" else token))


def keeps(typed, name):
    """the typed text names this subtype: its number, or 'type' with no number, and something of the disease's own name
    ('CHF NYHA III' has the number of 'hypertrophic cardiomyopathy 3' and nothing else of it)."""
    parsed = parse(name)
    if parsed is None: return True
    if not names_number(typed): return False
    stem, num = parsed; low = typed.lower()
    numbers = {_canon(x) for x in re.findall(rf"\b(?:{_ROM})\b|\d+[a-z]?\d?[a-z]?", low)}
    if numbers and _canon(num) not in numbers: return False
    if re.search("[가-힣]", typed): return True
    letters = re.sub(r"[^a-z]", "", stem.lower()); own = {w.lower() for w in _WORD.findall(stem)}
    def in_order(word):
        at = 0
        for ch in word:
            at = letters.find(ch, at) + 1
            if not at: return False
        return True
    words = [w for w in _WORD.findall(low) if w not in ("type", "subtype") and w not in ROMAN and w != "i"]
    return any(w in own or in_order(w) for w in words)


def general(concept):
    """the general concept's id for a numbered subtype; None for other ids and for a subtype without one."""
    row = general_map().get(concept)
    return row[1] if row else None


def is_subtype(concept): return concept in general_map()


_NAMES = {}


def general_name(general):
    if not _NAMES: _NAMES.update({v[1]: v[2] for v in general_map().values() if v[1]})
    return _NAMES[general]
