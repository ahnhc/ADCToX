"""Routine blood-test values, as printed on a lab report, turned into what the label rules and the organ order read.

Two uses, kept apart:
  1. label restrictions (ml/restrictions.py) read CLcr, bilirubin / AST / ALT as x ULN, platelets, ANC, HbA1c, LVEF.
     CLcr is Cockcroft-Gault from creatinine, age, sex and weight (the labels' measure). With eGFR only, eGFR stands in for
     CLcr and every result says so: the two are not the same quantity (eGFR is normalised to 1.73 m2, CLcr is not).
  2. an abnormal value marks an organ as vulnerable, like a condition does. Thresholds are CTCAE v5.0 grade 2 (or the
     cited clinical definition); the organ gets MONDO_SEVERITY, the same fixed value any non-registry condition gets, so no
     new weight is introduced. These flags never trigger condition-based label rules (they are not registry conditions).
Values a lab report prints that no ADC label uses (lipids, uric acid, ferritin, T3, free T4) are not asked for.
"""
from fractions import Fraction

# key, label, unit, group; ULN defaults are common adult reference upper limits, overridable with uln_<key>
FIELDS = [("age", "Age", "years", "Basic"), ("sex", "Sex", "M/F", "Basic"), ("weight", "Weight", "kg", "Basic"),
          ("creatinine", "Creatinine", "mg/dL", "Kidney"), ("egfr", "eGFR", "mL/min/1.73m²", "Kidney"),
          ("bilirubin", "Bilirubin", "mg/dL", "Liver"), ("ast", "AST", "U/L", "Liver"), ("alt", "ALT", "U/L", "Liver"),
          ("albumin", "Albumin", "g/dL", "Liver"), ("ggt", "GGT", "U/L", "Liver"), ("child_pugh", "Child-Pugh", "A/B/C", "Liver"),
          ("hb", "Hb", "g/dL", "Blood"), ("platelet", "Platelet", "x10³/µL", "Blood"), ("anc", "ANC", "x10³/µL", "Blood"),
          ("hba1c", "HbA1c (NGSP)", "%", "Glucose"), ("glucose", "Glucose (fasting)", "mg/dL", "Glucose"),
          ("amylase", "Amylase", "U/L", "Pancreas"), ("lipase", "Lipase", "U/L", "Pancreas"),
          ("tsh", "TSH", "µIU/mL", "Thyroid"),
          ("lvef", "LVEF", "%", "Cardio"), ("ugt1a1", "UGT1A1*28 homozygous", "y/n", "Genotype")]
RANGE = {"age": (1, 120), "weight": (1, 400), "creatinine": (0.05, 30), "egfr": (1, 200), "bilirubin": (0.01, 50), "ast": (1, 10000),
         "alt": (1, 10000), "albumin": (0.5, 7), "ggt": (1, 10000), "hb": (1, 25), "platelet": (1, 2000), "anc": (0.01, 100),
         "hba1c": (2, 25), "glucose": (10, 2000), "amylase": (1, 10000), "lipase": (1, 10000), "tsh": (0.001, 500), "lvef": (5, 90)}
ULN = {"bilirubin": 1.2, "ast": 40.0, "alt": 40.0, "ggt": 60.0, "amylase": 100.0, "lipase": 60.0}

# (key, test, organ, why) -- CTCAE v5.0 grade >= 2 unless stated
FLAGS = [("hb", lambda v, u: v < 10.0, "haematologic", "Hb < 10 g/dL (CTCAE anaemia G2)"),
         ("platelet", lambda v, u: v < 75.0, "haematologic", "platelets < 75 x10³/µL (CTCAE G2)"),
         ("anc", lambda v, u: v < 1.5, "haematologic", "ANC < 1.5 x10³/µL (CTCAE G2)"),
         ("hba1c", lambda v, u: v >= 6.5, "metabolic_endocrine", "HbA1c ≥ 6.5% (ADA diabetes)"),
         ("glucose", lambda v, u: v >= 126.0, "metabolic_endocrine", "fasting glucose ≥ 126 mg/dL (ADA diabetes)"),
         ("albumin", lambda v, u: v < 3.0, "hepatic", "albumin < 3.0 g/dL (CTCAE G2)"),
         ("ggt", lambda v, u: _xuln(v, u) > 2.5, "hepatic", "GGT > 2.5 x ULN (CTCAE G2)"),
         ("bilirubin", lambda v, u: _xuln(v, u) > 1.5, "hepatic", "bilirubin > 1.5 x ULN (CTCAE G2)"),
         ("ast", lambda v, u: _xuln(v, u) > 3.0, "hepatic", "AST > 3 x ULN (CTCAE G2)"),
         ("alt", lambda v, u: _xuln(v, u) > 3.0, "hepatic", "ALT > 3 x ULN (CTCAE G2)"),
         ("amylase", lambda v, u: _xuln(v, u) > 1.5, "gastrointestinal", "amylase > 1.5 x ULN (CTCAE G2)"),
         ("lipase", lambda v, u: _xuln(v, u) > 1.5, "gastrointestinal", "lipase > 1.5 x ULN (CTCAE G2)"),
         ("tsh", lambda v, u: v > 10.0 or v < 0.1, "metabolic_endocrine", "TSH > 10 or < 0.1 µIU/mL (overt thyroid dysfunction)")]


def parse(key, text):
    """one typed value -> number / letter, or None; raises ValueError on nonsense."""
    t = text.strip()
    if not t: return None
    if key == "sex":
        s = t.upper()[:1]
        if s in ("M", "F", "남", "여"): return {"남": "M", "여": "F"}.get(s, s)
        raise ValueError("M or F")
    if key == "child_pugh":
        if t.upper() in ("A", "B", "C"): return t.upper()
        raise ValueError("A, B or C")
    if key == "ugt1a1":
        if t.lower()[:1] in ("y", "n"): return t.lower()[:1] == "y"
        raise ValueError("y or n")
    try: v = float(t.replace(",", ""))
    except ValueError: raise ValueError("숫자를 입력하세요") from None
    lo, hi = RANGE.get(key, (float("-inf"), float("inf")))
    if not lo <= v <= hi: raise ValueError(f"{lo:g}–{hi:g}")
    return v


def _exact(x):
    return Fraction(repr(x)) if isinstance(x, float) else Fraction(x)      # the number as typed, not its binary float


def _xuln(v, u):
    return _exact(v) / _exact(u)


def cockcroft_gault(age, weight, creatinine, sex):
    """not rounded: the label thresholds compare the exact value; round only to show it."""
    return float((140 - _exact(age)) * _exact(weight) / (72 * _exact(creatinine)) * (Fraction(17, 20) if sex == "F" else 1))


def shown(key, v):
    """a derived value as the screen shows it: CLcr to 0.1 mL/min, x ULN to 0.01. A value that would show as a multiple of 0.5,
    where the label thresholds are (3 x ULN, CLcr 30), without being one gets more digits: 3.601 / 1.2 shows 3.001, not 3."""
    if key not in ("crcl", "bili", "ast", "alt") or not isinstance(v, float): return f"{v:g}"
    d = 1 if key == "crcl" else 2
    while d < 6 and round(v, d) != v and (round(v, d) * 2).is_integer(): d += 1
    return f"{round(v, d):g}"


def derive(raw, uln=None):
    """raw {key: value} -> (restriction inputs for ml/restrictions.Patient, [(organ, why)], [note lines])."""
    u = {**ULN, **(uln or {})}; lab, flags, notes = {}, [], []
    if all(raw.get(k) is not None for k in ("age", "weight", "creatinine", "sex")) and raw["creatinine"] > 0 and raw["age"] < 140:
        lab["crcl"] = cockcroft_gault(raw["age"], raw["weight"], raw["creatinine"], raw["sex"])
        notes.append(f"CLcr {shown('crcl', lab['crcl'])} mL/min (Cockcroft-Gault)")
    elif raw.get("egfr") is not None:
        lab["crcl"] = float(raw["egfr"]); notes.append(f"CLcr ≈ eGFR {raw['egfr']:g} (approximation; Creatinine + age, sex, weight give CLcr)")
    elif raw.get("creatinine") is not None:
        notes.append("Creatinine needs age, sex and weight for CLcr (or enter eGFR)")
    for k, dst in (("bilirubin", "bili"), ("ast", "ast"), ("alt", "alt")):
        if raw.get(k) is not None: lab[dst] = float(_xuln(raw[k], u[k]))     # not rounded (3.601 / 1.2 is above 3 x ULN)
    for k, dst in (("platelet", "platelets"), ("anc", "anc"), ("hba1c", "hba1c"), ("lvef", "lvef"), ("child_pugh", "child_pugh"), ("ugt1a1", "ugt1a1_28_homozygous")):
        if raw.get(k) is not None: lab[dst] = raw[k]
    for k, test, organ, why in FLAGS:
        if raw.get(k) is not None and test(raw[k], u.get(k)): flags.append((organ, why))
    if any(raw.get(k) is not None for k in ULN): notes.append("ULN used: " + ", ".join(f"{k} {u[k]:g}" for k in ULN if raw.get(k) is not None))
    return lab, flags, notes
