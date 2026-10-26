"""Tables for the Bio AI convergence contest (docs/competition_plan.md): the size of the problem, and the ADC payload/linker
table with each label's own mechanism text.

    ADC_RESEARCH_MODE=1 python ml/competition_tables.py
    -> data/curated/competition/adc_mechanism_draft.csv   one row per approved ADC: target, payload, family, mechanism, linker,
                                                          bystander, organs with a boxed warning or W&P and the label headings
                                                          behind them; `mechanism_note`: the label's own section 12.1
                                                          (Mechanism of Action), verbatim, with `reference`; nobody
                                                          paraphrases it, and `check` confirms it is on the label
       data/curated/competition/problem_size.json         organ -> ADCs with a boxed warning / W&P on it, and for common
                                                          comorbidities (their organs from the app's label table) the ADCs
                                                          whose warnings fall on those organs
Everything comes from the approved labels (ml/drug_evidence.py, DailyMed snapshot) and conf/adc_registry.yaml; nothing is imputed.
"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import yaml
import adc_paths as P, drug_evidence as D

OUT = P.REPO + "data/curated/competition/"
COMORB = ["chronic kidney disease", "cirrhosis of liver", "type 2 diabetes mellitus", "heart failure", "interstitial lung disease",
          "chronic obstructive pulmonary disease", "peripheral neuropathy", "essential hypertension", "glaucoma"]


def label_text(adc):
    """the latest label of an ADC as plain text (tags removed, entities decoded, white space collapsed)."""
    import html, re
    for d in [D.DM] + D.DM_ADDED:
        base = d + adc.replace("-", "_") + "/"
        if not os.path.isdir(base): continue
        v = max(int(m.group(1)) for f in os.listdir(base) if (m := re.match(r"v(\d+)\.html$", f)))
        t = open(base + f"v{v}.html", encoding="utf-8", errors="ignore").read()
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t))), v
    return "", None


def moa(text):
    """section 12.1 Mechanism of Action as printed on the label (the last occurrence: the first is the table of contents)."""
    i = text.rfind("12.1 Mechanism of Action")
    if i < 0: return ""
    j = text.find("12.2 ", i + 10); j = j if j > 0 else i + 3000
    return text[i + len("12.1 Mechanism of Action"):j].strip()


def check():
    """every filled mechanism_note must be a verbatim span of that ADC's label (the only check: no person reviews it)."""
    bad = []
    for r in csv.DictReader(open(OUT + "adc_mechanism_draft.csv", encoding="utf-8")):
        t, _ = label_text(r["adc"])
        if r["mechanism_note"] and r["mechanism_note"] not in t: bad.append(r["adc"])
    print("mechanism notes not found verbatim on the label:", bad or "none"); return not bad


def main():
    os.makedirs(OUT, exist_ok=True)
    reg = yaml.safe_load(open(P.REPO + "conf/adc_registry.yaml"))["agents"]; W = D.warnings(); rows = []
    for adc, w in sorted(W.items()):
        r = reg.get(adc.replace("-", "_"), {}); ax = w["axes"]
        lvl = lambda L: "; ".join(sorted(a for a, x in ax.items() if x["level"] == L))
        rows.append(dict(adc=adc, brand=w["brand"], label_version=w["version"], label_date=w["date"], target=r.get("target_label", ""),
                         payload=r.get("payload", ""), payload_family=r.get("payload_family", ""), mechanism=r.get("mechanism", ""),
                         linker=r.get("linker_type", ""), linker_cleavable=r.get("linker_cleavable", ""), bystander=r.get("bystander", ""),
                         boxed_organs=lvl("boxed"), wp_organs=lvl("W&P"),
                         label_headings=" | ".join(f"{a}: " + ", ".join(f"{s} {t}" for s, t in x["headings"]) for a, x in sorted(ax.items())),
                         mechanism_note=moa(label_text(adc)[0]), reference=f"{w['brand']} label v{label_text(adc)[1]}, section 12.1",
                         checked_by="verbatim match against the label text (ml/competition_tables.py check)"))
    with open(OUT + "adc_mechanism_draft.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
    by = {a: dict(boxed=sorted(k for k, w in W.items() if w["axes"].get(a, {}).get("level") == "boxed"),
                  wp=sorted(k for k, w in W.items() if w["axes"].get(a, {}).get("level") == "W&P")) for a in D.AXES}
    import mondo_index as MI
    from build_linking_pools import read_obo
    T = read_obo(); name = {}; MI.link(["x"])                                             # the app's own label table (every concept)
    for t, x in T.items():
        if t.startswith("MONDO:"):
            for n in [x["name"]] + x["syn"]: name.setdefault(n.lower(), t)
    com = {}
    for c in COMORB:
        t = name.get(c); org = sorted(MI.concept(t)[1]) if t else []
        hit = sorted({k for k, w in W.items() for a in org if a in w["axes"]})
        com[c] = dict(mondo=t, organs=org, adcs_with_warning_on_these_organs=hit, n=len(hit))
    res = dict(n_adcs=len(W), organ=by, organ_counts={a: dict(boxed=len(v["boxed"]), wp=len(v["wp"]), any=len(set(v["boxed"]) | set(v["wp"]))) for a, v in by.items()},
               comorbidities=com, source="approved labels (DailyMed snapshot via ml/drug_evidence.py); comorbidity organs from the app's label table")
    json.dump(res, open(OUT + "problem_size.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps(dict(n=res["n_adcs"], organ_counts={a: v for a, v in res["organ_counts"].items() if v["any"]},
                          comorbidities={c: (v["organs"], v["n"]) for c, v in com.items()}), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    check() if sys.argv[1:] == ["check"] else (main(), check())
