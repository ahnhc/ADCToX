"""ADC-side evidence per organ, as recorded on the approved labels. Nothing here is imputed.

warnings()   axis -> level ('boxed' | 'W&P') and the label headings behind it. Every axis a heading names counts
             (adctox.validation.label_change.axes_for_heading), and the boxed headline is split case-insensitively.
incidence()  axis -> the largest grade >= 3 incidence in the label's adverse-reaction tables (collaborator workbook,
             rows sourced 'Regulatory label via DailyMed'), with the term, table and regimen it came from.
             * aggregated within one table first: Grade 3 + Grade 4 rows are added only inside the same table (the
               first version added them across trials), a 'Grade 3-4' / 'Grade >=3' row is taken as is;
             * monotherapy rows are preferred; an axis known only from combination tables is marked combo=True;
             * lab-abnormality tables are marked lab=True (e.g. amylase counts as gastrointestinal in the workbook);
             * an ADC with no label table returns None for every axis ('no data'), an axis absent from the tables of
               an ADC that has them returns status 'not reported' (tables are threshold-limited). Neither is 0.
"""
import json, os, re, sys, pathlib
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from adctox.validation.label_change import parse_version, axes_for_heading

C = "/data/hyeongchanahn/adctox/ml_cache/"; DM = "/data/hyeongchanahn/adctox/raw/dailymed/2026-10-07/"
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular",
        "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
DOM = {"Cardiac": "cardiovascular", "Vascular": "cardiovascular", "Skin": "dermatologic", "Metabolic": "metabolic_endocrine", "Endocrine": "metabolic_endocrine",
       "Renal": "renal", "Hematologic": "haematologic", "Pulmonary": "pulmonary", "Ocular": "ocular", "Hepatic": "hepatic", "GI": "gastrointestinal",
       "Neurologic": "neurologic", "Musculoskeletal": "musculoskeletal", "Infection": "infectious_immune", "Immune": "infectious_immune"}
SEVERE_CUM, SEVERE_PART = ["Grade 3-4", "Grade >=3"], ["Grade 3", "Grade 4"]


def warnings():
    """{adc: dict(version, date, brand, axes={axis: dict(level, headings=[(section, text)])})} for every ADC in the snapshot."""
    man = json.load(open(DM + "_manifest.json"))["agents"]; out = {}
    for agent in sorted(man):
        vs = sorted(int(m.group(1)) for f in os.listdir(DM + agent) if (m := re.match(r"v(\d+)\.html$", f))); v = vs[-1]
        lv = parse_version(pathlib.Path(DM + f"{agent}/v{v}.html"), agent, v, None); ax = {}
        for sec, head in lv.sec5.items():
            for a in axes_for_heading(head):
                if a in AXES: ax.setdefault(a, dict(level="W&P", headings=[]))["headings"].append((sec, head))
        if lv.boxed_headline:
            for part in re.split(r"\band\b|,|;", lv.boxed_headline[len("WARNING"):].lstrip(": "), flags=re.IGNORECASE):
                for a in axes_for_heading(part):
                    if a in AXES:
                        e = ax.setdefault(a, dict(level="boxed", headings=[])); e["level"] = "boxed"; e["headings"].insert(0, ("Boxed", part.strip()))
        date = next((x["date"] for x in man[agent]["versions"] if x["version"] == v), None)
        out[agent.replace("_", "-")] = dict(version=v, date=date, brand=man[agent].get("brand"), axes=ax)
    return out


def incidence():
    """{adc: {axis: dict(pct, term, grade, table, combo, lab)} } for ADCs with label tables; ADCs without are absent."""
    t = pd.read_pickle(C + "tox.pkl")
    L = t[(t["Canonical observation"].astype(str) == "True") & (t["Source type"] == "Regulatory label via DailyMed")].copy()
    L["pct"] = pd.to_numeric(L["Incidence percent"], errors="coerce"); L = L.dropna(subset=["pct"])
    L["term"] = L["Raw AE term"].astype(str).str.lower().str.strip(); L["table"] = L["Source table"].astype(str).str.replace(r";\s*row \d+$", "", regex=True)
    L["axis"] = L["Toxicity domain"].astype(str).str.split(" / ").str[0].map(DOM); L["mono"] = L["Monotherapy"].astype(str) == "Yes"
    key = ["ADC ID", "table", "term", "axis", "mono"]
    cum = L[L["Grade category"].isin(SEVERE_CUM)].groupby(key).pct.max().rename("r")
    part = L[L["Grade category"].isin(SEVERE_PART)].groupby(key).pct.sum().rename("r")           # grades 3 and 4 are disjoint WITHIN a table
    both = pd.concat([cum, part]).groupby(level=list(range(len(key)))).max().reset_index()
    grade = L[L["Grade category"].isin(SEVERE_CUM + SEVERE_PART)].groupby(key)["Grade category"].agg(lambda g: "/".join(sorted(set(g))))
    both = both.merge(grade.rename("grade").reset_index(), on=key).dropna(subset=["axis"])
    out = {a: {} for a in L["ADC ID"].unique()}
    for (adc, ax), g in both.groupby(["ADC ID", "axis"]):
        pool = g[g.mono] if g.mono.any() else g; r = pool.sort_values("r", ascending=False).iloc[0]
        out[adc][ax] = dict(pct=float(r.r), term=r.term, grade=r.grade, table=r.table, combo=not bool(g.mono.any()), lab="laborator" in r.table.lower())
    return out


def evidence():
    """one record per ADC in the label snapshot: warnings + incidence + data status."""
    W, I = warnings(), incidence(); ms = pd.read_pickle(C + "master.pkl").drop_duplicates("ADC ID").set_index("ADC ID"); out = {}
    for adc, w in W.items():
        inc = I.get(adc); rows = {}
        for a in AXES:
            lv = w["axes"].get(a, {}).get("level", "none")
            if inc is None: st, x = "no data", None
            elif a in inc: st, x = "reported", inc[a]
            else: st, x = "not reported", None
            rows[a] = dict(level=lv, headings=w["axes"].get(a, {}).get("headings", []), inc_status=st, inc=x)
        name = ms.loc[adc, "ADC name"] if adc in ms.index else adc.replace("-", " ").capitalize()
        out[adc] = dict(name=name, version=w["version"], date=w["date"], brand=w["brand"], has_tables=inc is not None, organs=rows)
    return out


if __name__ == "__main__":
    E = evidence()
    for adc, e in E.items():
        print(f"{e['name']:28s} v{e['version']} {e['date']}  tables={e['has_tables']}")
        for a, r in e["organs"].items():
            if r["level"] != "none" or r["inc_status"] == "reported":
                x = r["inc"]; inc = f"{x['pct']:.1f}% {x['term']}{' [combo]' if x['combo'] else ''}{' [lab]' if x['lab'] else ''}" if x else r["inc_status"]
                print(f"    {a:20s} {r['level']:5s}  {inc}")
