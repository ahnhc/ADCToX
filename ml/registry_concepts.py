"""Which registry condition a concept the organ judge links to stands for.

    python -I ml/registry_concepts.py          -> conf/registry_concepts.json

The judge (models 0.7+) links typed text to a MONDO or HPO concept and judges its organs. A registry condition adds what the
judge does not give: its severity and the restriction rules keyed on it. ANCHORS names, per registry condition, the concepts
that mean it; "ID>" also takes every is_a descendant (MONDO, HPO), "ID" the concept alone (a broad grouping such as
'autoimmune disease' would otherwise take hundreds of diseases), "!ID" leaves that concept and its descendants out of the
condition (MONDO files primary biliary cholangitis under cirrhosis). A concept under several anchors goes to the nearest one
('diabetic neuropathy' is under 'peripheral neuropathy'), ties to the earlier condition in the registry. Prior exposures,
procedures and measurements (reduced LVEF) have no anchor: they are picked from the list.

The registry's own mondo_id column stays as it was (an older audit accepts a broader term on the same organ there, and
scripts/derive_organ_axes.py reads it); it is not used for this match.
"""
import csv, json, os, sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P

REGISTRY = P.REPO + "conf/comorbidity_registry.csv"
OUT = P.REPO + "conf/registry_concepts.json"
MONDO_OBO = P.REPO + "data/raw_big/mondo/2026-10-07/mondo.obo"
HP_OBO = P.REPO + "data/raw/hpo/hp.obo"

ANCHORS = {
    "chronic_liver_disease": ["MONDO:0100193>", "HP:0100626>", "MONDO:0005154"],    # chronic liver failure; 'liver disorder' alone
    "cirrhosis": ["MONDO:0005155>", "HP:0001394>", "!MONDO:0005388"],             # not primary biliary cholangitis
    "hepatitis_b_chronic": ["MONDO:0005366>", "MONDO:0005344"],                     # chronic HBV infection; 'HBV infection' alone
    "hepatitis_c_chronic": ["MONDO:0005354>", "MONDO:0005231"],
    "hepatic_vod_history": ["MONDO:0019514>"],
    "nafld": ["MONDO:0013209>"],
    "ckd_stage_3": ["HP:0012625>", "MONDO:0005300", "HP:0012622"],                  # stage 3; unstaged CKD alone
    "ckd_stage_4_5": ["HP:0012626>", "HP:0003774>"],                                # stage 4, stage 5
    "dialysis": ["MONDO:0004375>", "MONDO:0975708"],                                # end stage renal failure (the label rules' esrd counts dialysis); dialysis disequilibrium syndrome
    "heart_failure": ["MONDO:0005252>"],
    "reduced_lvef": [],
    "prior_anthracycline": [],
    "coronary_artery_disease": ["MONDO:0005010>"],
    "qt_prolongation": ["HP:0001657>", "MONDO:0002442>"],
    "interstitial_lung_disease": ["MONDO:0015925>"],
    "pulmonary_fibrosis": ["MONDO:0002771>", "HP:0002206>"],
    "copd": ["MONDO:0005002>"],
    "prior_chest_radiation": [],
    "peripheral_neuropathy": ["MONDO:0005244>", "HP:0009830>"],
    "diabetic_neuropathy": ["MONDO:0006626>"],
    "multiple_sclerosis": ["MONDO:0005301>"],
    "keratopathy_history": ["MONDO:0002261>"],
    "dry_eye": ["MONDO:0006733>"],
    "glaucoma": ["MONDO:0005041>", "HP:0000501>"],
    "prior_corneal_surgery": [],
    "thrombocytopenia": ["MONDO:0002049>", "HP:0001873>"],
    "itp": ["MONDO:0002048>"],
    "neutropenia_chronic": ["MONDO:0001475>", "HP:0001875>"],
    "anaemia_chronic": ["MONDO:0002280>", "HP:0001903>"],
    "mds": ["MONDO:0018881>"],
    "prior_hsct": [],
    "inflammatory_bowel_disease": ["MONDO:0005011>", "MONDO:0005101>", "MONDO:0005265"],   # Crohn, UC; MONDO's IBD takes every colitis
    "prior_bowel_resection": [],
    "chronic_pancreatitis": ["MONDO:0005003>"],
    "severe_psoriasis": ["MONDO:0005083>"],
    "prior_sjs_ten": ["MONDO:0019810>", "MONDO:0018229>"],
    "type_2_diabetes": ["MONDO:0005148>"],
    "hypothyroidism": ["MONDO:0005420>", "HP:0000821>"],
    "hiv_controlled": ["MONDO:0005109>"],
    "active_autoimmune": ["MONDO:0007179"],
    "hearing_loss": ["MONDO:0005365>", "HP:0000407>"],
}


def read_obo(path):
    """-> {id: (name, [is_a parents])}, obsolete terms left out."""
    T, cur = {}, None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("["): cur = None; continue
        if line.startswith("id: "): cur = line[4:].strip(); T[cur] = ["", [], False]
        elif cur is None: continue
        elif line.startswith("name: "): T[cur][0] = line[6:].strip()
        elif line.startswith("is_a: "): T[cur][1].append(line[6:].split()[0])
        elif line == "is_obsolete: true": T[cur][2] = True
    return {t: (n, ps) for t, (n, ps, obs) in T.items() if not obs}


def build(T, registry_ids):
    """-> {concept: registry id}: each concept to the nearest anchor among its is_a ancestors (itself at distance 0)."""
    assert set(ANCHORS) == set(registry_ids), set(ANCHORS) ^ set(registry_ids)
    anchor = {}                                                    # concept -> [(registry order, id, descendants too)]
    for k, rid in enumerate(registry_ids):
        for a in ANCHORS[rid]:
            if a.startswith("!"): assert a[1:] in T, f"{rid}: {a[1:]} is not in the ontology"; continue
            t, deep = a.rstrip(">"), a.endswith(">")
            assert t in T, f"{rid}: {t} is not in the ontology"
            anchor.setdefault(t, []).append((k, rid, deep))
    children = {}
    for t, (_, ps) in T.items():
        for p in ps: children.setdefault(p, []).append(t)
    best = {}                                                      # concept -> (distance, registry order, id)
    for t, rows in anchor.items():
        for k, rid, deep in rows:
            skip = {a[1:] for a in ANCHORS[rid] if a.startswith("!")}
            seen, todo = {t} | skip, deque([(t, 0)])
            while todo:
                c, d = todo.popleft()
                if "non-human animal" not in T[c][0] and (c not in best or (d, k) < best[c][:2]): best[c] = (d, k, rid)
                if deep:
                    for ch in children.get(c, []):
                        if ch not in seen: seen.add(ch); todo.append((ch, d + 1))
                elif c == t: break
    return {c: rid for c, (_, _, rid) in sorted(best.items())}


def main():
    ids = [r["id"] for r in csv.DictReader(open(REGISTRY, encoding="utf-8"))]
    T = {**read_obo(MONDO_OBO), **read_obo(HP_OBO)}
    m = build(T, ids)
    json.dump(dict(source=dict(mondo=os.path.relpath(MONDO_OBO, P.REPO), hp=os.path.relpath(HP_OBO, P.REPO)), anchors=ANCHORS, concepts=m),
              open(OUT, "w", encoding="utf-8"), indent=0, ensure_ascii=False)
    n = {}
    for rid in m.values(): n[rid] = n.get(rid, 0) + 1
    print(f"{len(m)} concepts -> {len(n)} registry conditions:", ", ".join(f"{r} {n.get(r, 0)}" for r in ids if ANCHORS[r]))


if __name__ == "__main__":
    main()
