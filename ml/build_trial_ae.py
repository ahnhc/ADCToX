"""ClinicalTrials.gov results of the ADCs' main trials -> per organ, the most frequent adverse event in the ADC arm.

  python3 ml/build_trial_ae.py   -> data/curated/competition/trial_ae.json
      {"snapshot": ..., "adcs": {adc: {"trials": [trial, ...], "no_results": [{trial, nct}, ...]}}}
      trial = {nct, trial, phase, population, regimen, labelled, n, serious: [affected, at_risk], threshold, comparator: {regimen, n} | null,
               organs: {axis: {"any": event, "serious": event, "warned": [event, event]}}}      (organ_events() says which)
      event = {term, a, n, comp: [a, n] | null, sa: serious count | null, serious: true when reported only as serious}

data/curated/competition/adc_trials.csv names the trials (the team's list of 2026-10-29, 32 rows, 31 studies) and, for each, the event
groups that received the ADC as the label indicates it (`groups`, summed when one regimen was split into cohorts) and the comparator
groups (`comparator_groups`). `labelled` = n marks a regimen or population the current US label does not indicate (DREAMM-2 single
agent, DREAMM-8, TROPION-Lung01); `cancers` names the trial's cancer as adc_cancers.csv names it. The app shows the trial of the
patient's cancer when one is known, else a labelled trial, the largest first. A trial with no `groups` has no results posted on
ClinicalTrials.gov (ALFA-0701, POLARIX, LUMINOSITY).

The records come from the project's ClinicalTrials.gov snapshot (studies/<NCT>.json, ADCTOX_CTGOV overrides the directory). An
event's organ is conf/ontology/axes.yaml (MedDRA system organ class -> axis) with the Investigations terms redistributed by
conf/ontology/investigations_rules.yaml, the same mapping the research corpus uses (src/adctox/taxonomy.py). Per axis the event with
the highest rate in the ADC arm is kept, once among the non-serious events (reported at or above the trial's frequency threshold,
usually 5%) and once among the serious events (all reported), and up to two events the label warnings on that organ are about
(SIGNAL); the same event's count in the comparator arm comes along. Event terms are quoted as the records print them, lowercased.
Rates are never added across events: one patient can have several."""
import csv, json, os, sys

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..") + os.sep
sys.path.insert(0, R + "src")
from adctox.taxonomy import default_taxonomy
from adctox.extract.arm_resolver import Registry, resolve_study
TRIALS = R + "data/curated/competition/adc_trials.csv"
INDICATIONS = R + "data/curated/competition/adc_indications.csv"
CANCERS = R + "data/curated/competition/adc_cancers.csv"
STUDIES = os.environ.get("ADCTOX_CTGOV") or "/data/hyeongchanahn/adctox/raw/ctgov/2026-10-07/studies/"
OUT = R + "data/curated/competition/trial_ae.json"
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular",
        "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]


# The events the labels' section 5 warnings on each organ are about: per axis, (warning heading pattern, event term pattern) topics
# in the order they are shown. An ADC's warned events are the topics its own headings on that organ name (ml/drug_evidence.warnings();
# 'Left Ventricular Dysfunction' -> ejection fraction, cardiac failure; 'Hemorrhage' -> epistaxis, haematoma), one event per topic.
# Matched on the term whatever system organ class the sponsor filed it under: DESTINY-Breast03 files 'Pneumonitis' under
# infections, innovaTV 301 'Conjunctivitis' too.
SIGNAL = {"haematologic": [("neutropeni|hematologic|myelosuppress", r"neutropeni|neutrophil count|leukopeni|white blood cell"),
                           ("thrombocytopeni|hematologic|myelosuppress", r"thrombocytopeni|platelet count"),
                           ("hematologic|myelosuppress", r"an(a)?emia|h(a)?emoglobin|pancytopeni|lymphopeni|lymphocyte count")],
          "hepatic": [("hepatotox|hepatic", r"hepat|liver|alanine aminotrans|aspartate aminotrans|transaminase|bilirubin|gamma.?glutamyl|alkaline phosphatase"),
                      ("veno-occlusive|sinusoidal", r"veno.?occlusive|sinusoidal obstruction")],
          "cardiovascular": [("ventricular|cardiac|cardiomyopath", r"ejection fraction|ventricular dysfunction|cardiac failure|heart failure|cardiomyopath|left ventricular"),
                             ("qt", r"qt prolong|electrocardiogram qt"),
                             ("hemorrhage|haemorrhage|bleeding", r"h(a)?emorrhag|bleeding|epistaxis|h(a)?ematoma"),
                             ("edema|effusion|capillary", r"oedema|edema|effusion|capillary leak")],
          "pulmonary": [("interstitial|pneumonitis|pulmonary", r"interstitial lung|pneumonitis|pulmonary fibrosis|organi[sz]ing pneumonia|respiratory failure|acute respiratory distress|pulmonary toxicity|lung infiltration|hypoxia")],
          "renal": [("renal", r"acute kidney injury|renal failure|renal impairment|creatinine|proteinuria|nephr")],
          "gastrointestinal": [("diarrhea", r"diarrh|colitis"), ("stomatitis|mucos", r"stomatitis|mucosal inflammation|mucositis"),
                               ("nausea|vomiting", r"nausea|vomiting"),
                               ("gastrointestinal", r"gastrointestinal perforation|intestinal (perforation|obstruction)|ileus|pancreatitis|lipase|amylase|gastrointestinal h(a)?emorrhage")],
          "neurologic": [("neuropathy|neurotox", r"neuropath|neurotox|par(a)?esthesia|guillain"), ("leukoencephalopathy|pml", r"leukoencephalopathy|\bpml\b"),
                         ("neurotox", r"seizure|encephalopath|cerebrovascular")],
          "ocular": [("ocular|eye|kerat|corneal|visual", r"kerat|ocular|corneal|vision|visual|dry eye|conjunctiv|blepharitis|cataract|uveitis|\beye\b|photophobia|lacrimation|blindness")],
          "dermatologic": [("skin|cutaneous|dermatolog", r"\brash|stevens|epidermal necrolysis|cutaneous|\bskin|dermatitis|pruritus|alopecia|erythema|hand.?foot|palmar|exfoliat|drug reaction with eosinophilia|bullous|pemphig")],
          "metabolic_endocrine": [("hyperglyc", r"hyperglyc|blood glucose increased|diabet|ketoacidosis"), ("tumor lysis", r"tumou?r lysis"),
                                  ("(?!x)x", r"hypokal|hyponatr|hypophosphat|hypomagnes|hypocalc|thyroid")],
          "musculoskeletal": [],
          "infectious_immune": [("infusion|anaphyla|hypersensitivity|allergic", r"infusion.?related|anaphyla|hypersensitivity"),
                                ("infection", r"infection|sepsis|septic|pneumonia|bacter|viral|fungal|cytomegalovirus|herpes|covid|opportunistic")],
          "otologic": [("ototox|hearing", r"hearing|deaf|tinnitus|ototox|vertigo")]}


EXCLUDE = r"cancer|carcinoma|neoplasm|malignan|metasta|radiation"   # a tumour or radiotherapy is not an adverse reaction of the drug ('skin cancer', 'hypercalcaemia of malignancy', 'radiation pneumonitis')


def topics(axis, headings):
    """the term patterns for an ADC's headings on the axis (SIGNAL order); none when no heading names a topic (the app then shows
    the organ's most frequent event and its most frequent serious event)"""
    import re
    return [t for h, t in SIGNAL[axis] if any(re.search(h, x, re.I) for x in headings)]


def counts(event, gids):
    """(affected, at risk) of one event summed over the groups; None when no group reports it"""
    st = [s for s in event.get("stats", []) if s.get("groupId") in gids and s.get("numAtRisk")]
    return (sum(s.get("numAffected", 0) for s in st), sum(s["numAtRisk"] for s in st)) if st else None


def organ_events(ae, gids, comp, tax, headings):
    """axis -> {any: the most frequent non-serious event, serious: the most frequent serious event, warned: up to two events the
    ADC's label warnings on this organ are about (topics(); the most frequent event of each topic)}; each event = {term, a, n, comp,
    sa, serious} (a/n in the ADC groups, comp the same event's [a, n] in the comparator groups, sa the serious count of the same term).
    headings: axis -> the ADC's warning headings on it."""
    import re
    serious_of = {}
    for e in ae.get("seriousEvents", []):
        c = counts(e, gids)
        if c: serious_of[e["term"].strip().lower()] = c[0]
    rows = []
    for kind, events in (("other", ae.get("otherEvents", [])), ("serious", ae.get("seriousEvents", []))):
        for e in events:
            c = counts(e, gids); term = e["term"].strip().lower()
            if not c or not c[0] or re.search(EXCLUDE, term): continue
            cc = counts(e, comp) if comp else None
            rows.append((kind, tax.resolve(e.get("term"), e.get("organSystem"))[0], c[0] / c[1],
                         dict(term=term, a=c[0], n=c[1], comp=list(cc) if cc else None, sa=serious_of.get(term), serious=kind == "serious")))
    out = {}
    for axis in AXES:
        other = sorted((r for r in rows if r[0] == "other" and r[1] == axis), key=lambda r: -r[2])
        ser = sorted((r for r in rows if r[0] == "serious" and r[1] == axis), key=lambda r: -r[2])
        warned, seen = [], set()
        for pattern in topics(axis, headings.get(axis, [])):
            hit = sorted((r for r in rows if re.search(pattern, r[3]["term"]) and r[3]["term"] not in seen), key=lambda r: (r[0] == "serious", -r[2]))
            if hit: seen.add(hit[0][3]["term"]); warned.append(hit[0][3])          # the topic's most frequent event, all grades before serious-only
        o = {k: v for k, v in (("any", other[0][3] if other else None), ("serious", ser[0][3] if ser else None), ("warned", warned[:2])) if v}
        if o: out[axis] = o
    return out


def trial(row, study, reg, headings):
    ae = study["resultsSection"]["adverseEventsModule"]; groups = {g["id"]: g for g in ae["eventGroups"]}
    gids = row["groups"].split(";"); comp = [g for g in row["comparator_groups"].split(";") if g]
    agent = row["adc"].replace("-", "_"); named = {a.group_id: {a.agent, *a.combo_agents} for a in resolve_study(study, reg)}
    for g in gids: assert agent in named[g], (row["nct"], g)                     # the ADC arm names the ADC (title, description or its arm group)
    for g in comp: assert agent not in reg.find_agents(groups[g]["title"]), (row["nct"], g)
    n = sum(groups[g].get("otherNumAtRisk") or 0 for g in gids)
    serious = [sum(groups[g].get("seriousNumAffected") or 0 for g in gids), sum(groups[g].get("seriousNumAtRisk") or 0 for g in gids)]
    organs = organ_events(ae, gids, comp, default_taxonomy(), headings)
    return dict(nct=row["nct"], trial=row["trial"], phase=row["phase"], population=row["population"], cancers=[c for c in row["cancers"].split(";") if c], regimen=row["regimen"],
                labelled=row["labelled"] == "y", n=n, serious=serious, threshold=float(ae.get("frequencyThreshold") or 0),
                comparator=dict(regimen=row["comparator"], n=sum(groups[g].get("otherNumAtRisk") or 0 for g in comp)) if comp else None, organs=organs)


def build():
    reg = Registry.load(); adcs = {r["adc"] for r in csv.DictReader(open(INDICATIONS, encoding="utf-8"))}
    known = {r["cancer"] for r in csv.DictReader(open(CANCERS, encoding="utf-8"))}
    sys.path.insert(0, R + "ml"); import drug_evidence as DE
    W = {adc: {axis: [h for _, h in d.get("headings", [])] for axis, d in w["axes"].items()} for adc, w in DE.warnings().items()}
    assert adcs <= set(W), adcs - set(W)
    out = {a: dict(trials=[], no_results=[]) for a in sorted(adcs)}
    for row in csv.DictReader(open(TRIALS, encoding="utf-8")):
        assert row["adc"] in adcs and set(row["cancers"].split(";")) <= known | {""}, (row["adc"], row["cancers"])
        if not row["groups"]:
            assert not os.path.exists(STUDIES + row["nct"] + ".json") or "resultsSection" not in json.load(open(STUDIES + row["nct"] + ".json")), row["nct"]
            out[row["adc"]]["no_results"].append(dict(trial=row["trial"], nct=row["nct"])); continue
        out[row["adc"]]["trials"].append(trial(row, json.load(open(STUDIES + row["nct"] + ".json", encoding="utf-8")), reg, W[row["adc"]]))
    for a in out: out[a]["trials"].sort(key=lambda t: (not t["labelled"], -t["n"]))
    assert all(v["trials"] or v["no_results"] for v in out.values()), "an ADC has no trial"
    doc = dict(snapshot="ClinicalTrials.gov " + os.path.basename(os.path.dirname(STUDIES.rstrip("/"))), adcs=out)
    json.dump(doc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return doc


if __name__ == "__main__":
    doc = build()
    for a, v in doc["adcs"].items():
        for t in v["trials"]:
            print(f"{a:<26} {t['trial']:<17} n={t['n']:<4} {'labelled' if t['labelled'] else 'other   '} organs={len(t['organs'])}")
        for t in v["no_results"]: print(f"{a:<26} {t['trial']:<17} no results posted")
    print(f"-> {os.path.relpath(OUT, R)} ({os.path.getsize(OUT) // 1024} KB)")
