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
# key, label, unit, group; ULN defaults are common adult reference upper limits, overridable with uln_<key>
FIELDS = [("age", "Age", "years", "Basic"), ("sex", "Sex", "M/F", "Basic"), ("weight", "Weight", "kg", "Basic"),
          ("creatinine", "Creatinine", "mg/dL", "Kidney"), ("egfr", "eGFR", "mL/min/1.73m²", "Kidney"),
          ("bilirubin", "Bilirubin", "mg/dL", "Liver"), ("ast", "AST", "U/L", "Liver"), ("alt", "ALT", "U/L", "Liver"),
          ("albumin", "Albumin", "g/dL", "Liver"), ("ggt", "GGT", "U/L", "Liver"),
          ("hb", "Hb", "g/dL", "Blood"), ("platelet", "Platelet", "x10³/µL", "Blood"), ("anc", "ANC", "x10³/µL", "Blood"),
          ("hba1c", "HbA1c (NGSP)", "%", "Glucose"), ("glucose", "Glucose (fasting)", "mg/dL", "Glucose"),
          ("amylase", "Amylase", "U/L", "Pancreas"), ("lipase", "Lipase", "U/L", "Pancreas"),
          ("tsh", "TSH", "µIU/mL", "Thyroid"),
          ("lvef", "LVEF", "%", "Other"), ("child_pugh", "Child-Pugh", "A/B/C", "Other"), ("ugt1a1", "UGT1A1*28 homozygous", "y/n", "Other")]
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
         ("ggt", lambda v, u: v > 2.5 * u, "hepatic", "GGT > 2.5 x ULN (CTCAE G2)"),
         ("bilirubin", lambda v, u: v > 1.5 * u, "hepatic", "bilirubin > 1.5 x ULN (CTCAE G2)"),
         ("ast", lambda v, u: v > 3.0 * u, "hepatic", "AST > 3 x ULN (CTCAE G2)"),
         ("alt", lambda v, u: v > 3.0 * u, "hepatic", "ALT > 3 x ULN (CTCAE G2)"),
         ("amylase", lambda v, u: v > 1.5 * u, "gastrointestinal", "amylase > 1.5 x ULN (CTCAE G2)"),
         ("lipase", lambda v, u: v > 1.5 * u, "gastrointestinal", "lipase > 1.5 x ULN (CTCAE G2)"),
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
    v = float(t.replace(",", ""))
    lo, hi = RANGE.get(key, (float("-inf"), float("inf")))
    if not lo <= v <= hi: raise ValueError(f"{lo:g}–{hi:g}")
    return v


def cockcroft_gault(age, weight, creatinine, sex):
    return (140 - age) * weight / (72 * creatinine) * (0.85 if sex == "F" else 1.0)


def derive(raw, uln=None):
    """raw {key: value} -> (restriction inputs for ml/restrictions.Patient, [(organ, why)], [note lines])."""
    u = {**ULN, **(uln or {})}; lab, flags, notes = {}, [], []
    if all(raw.get(k) is not None for k in ("age", "weight", "creatinine", "sex")) and raw["creatinine"] > 0 and raw["age"] < 140:
        lab["crcl"] = round(cockcroft_gault(raw["age"], raw["weight"], raw["creatinine"], raw["sex"]), 1)
        notes.append(f"CLcr {lab['crcl']:g} mL/min (Cockcroft-Gault)")
    elif raw.get("egfr") is not None:
        lab["crcl"] = float(raw["egfr"]); notes.append(f"CLcr ≈ eGFR {raw['egfr']:g} (approximation; Creatinine + age, sex, weight give CLcr)")
    elif raw.get("creatinine") is not None:
        notes.append("Creatinine needs age, sex and weight for CLcr (or enter eGFR)")
    for k, dst in (("bilirubin", "bili"), ("ast", "ast"), ("alt", "alt")):
        if raw.get(k) is not None: lab[dst] = round(raw[k] / u[k], 2)
    for k, dst in (("platelet", "platelets"), ("anc", "anc"), ("hba1c", "hba1c"), ("lvef", "lvef"), ("child_pugh", "child_pugh"), ("ugt1a1", "ugt1a1_28_homozygous")):
        if raw.get(k) is not None: lab[dst] = raw[k]
    for k, test, organ, why in FLAGS:
        if raw.get(k) is not None and test(raw[k], u.get(k)): flags.append((organ, why))
    if any(raw.get(k) is not None for k in ULN): notes.append("ULN used: " + ", ".join(f"{k} {u[k]:g}" for k in ULN if raw.get(k) is not None))
    return lab, flags, notes
