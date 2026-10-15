"""Organ votes for every MONDO concept from sources other than the MONDO is_a crosswalk, used as features of the organ model.

    python ml/organ_votes.py          -> $ADCTOX_CACHE/organ_votes.npz  (ids, V: concepts x 4 sources x 13 axes, sources)

  icd   ICD-10-CM / ICD-9 xrefs of the concept, by chapter range (axis_reliability.ICD_AXIS, axis_source_compare.ICD9_AXIS)
  mesh  MeSH descriptor xrefs -> tree numbers under the disease-category descriptors below (MeSH 2026, NLM, public domain)
  doid  Disease Ontology xrefs -> DOID is_a ancestors among the body-system classes below (DOID, CC0)
  hpo   OMIM / Orphanet xrefs -> HPO annotations (hpoa.tsv) -> share of the phenotypes in each HPO organ branch (HPO, custom open licence)
A vote is 0/1 (icd, mesh, doid) or a share 0-1 (hpo). None of them reads the labels or the gold.
"""
import collections, gzip, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P
from build_linking_pools import read_obo

AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
SOURCES = ["icd", "mesh", "doid", "hpo"]
OBO = P.REPO + "data/raw_big/mondo/2026-10-07/mondo.obo"
MESH = P.REPO + "data/raw/mesh/2026-10-15/desc2026.gz"; DOID = P.REPO + "data/raw/doid/2026-10-15/doid.obo"
HPOA = P.REPO + "data/raw_big/mondo/2026-10-07/hpoa.tsv"; HP = P.REPO + "data/raw/hpo/hp.obo"
MESH_AXIS = {"Hematologic Diseases": "haematologic", "Liver Diseases": "hepatic", "Biliary Tract Diseases": "hepatic",
             "Cardiovascular Diseases": "cardiovascular", "Respiratory Tract Diseases": "pulmonary", "Kidney Diseases": "renal",
             "Gastrointestinal Diseases": "gastrointestinal", "Pancreatic Diseases": "gastrointestinal", "Nervous System Diseases": "neurologic",
             "Eye Diseases": "ocular", "Skin Diseases": "dermatologic", "Endocrine System Diseases": "metabolic_endocrine",
             "Nutritional and Metabolic Diseases": "metabolic_endocrine", "Musculoskeletal Diseases": "musculoskeletal",
             "Immune System Diseases": "infectious_immune", "Infections": "infectious_immune", "Ear Diseases": "otologic"}
DOID_AXIS = {"hematopoietic system disease": "haematologic", "liver disease": "hepatic", "biliary tract disease": "hepatic",
             "cardiovascular system disease": "cardiovascular", "respiratory system disease": "pulmonary", "kidney disease": "renal",
             "gastrointestinal system disease": "gastrointestinal", "nervous system disease": "neurologic", "eye disease": "ocular",
             "eye and adnexa disease": "ocular", "integumentary system disease": "dermatologic", "skin disease": "dermatologic",
             "endocrine system disease": "metabolic_endocrine", "disease of metabolism": "metabolic_endocrine",
             "musculoskeletal system disease": "musculoskeletal", "immune system disease": "infectious_immune",
             "disease by infectious agent": "infectious_immune", "ear disease": "otologic", "middle ear disease": "otologic", "inner ear disease": "otologic"}


def xrefs():
    out, cur = collections.defaultdict(list), None
    for line in open(OBO, encoding="utf-8"):
        if line.startswith("id: "): cur = line[4:].strip()
        elif line.startswith("xref: ") and cur and cur.startswith("MONDO:"):
            x = line[6:].split()[0]
            if x.split(":")[0] in ("ICD10CM", "ICD9", "MESH", "DOID", "OMIM", "Orphanet"): out[cur].append(x)
    return out


def icd_votes(codes):
    from axis_reliability import ICD_AXIS
    from axis_source_compare import ICD9_AXIS
    v = np.zeros(len(AXES))
    for c in codes:
        s, code = c.split(":", 1)
        if s == "ICD10CM":
            k = code[:3].upper()
            for lo, hi, a in ICD_AXIS:
                if lo <= k <= hi: v[AXES.index(a)] = 1
        elif s == "ICD9" and re.match(r"^\d{3}", code):
            n = int(code[:3])
            for lo, hi, a in ICD9_AXIS:
                if lo <= n <= hi: v[AXES.index(a)] = 1
    return v


def mesh_tree():
    """descriptor UI -> set of axes, from the tree numbers under the category descriptors of MESH_AXIS."""
    trees, name = {}, {}
    xml = gzip.open(MESH, "rt", encoding="utf-8").read()
    for rec in re.finditer(r"<DescriptorRecord .*?</DescriptorRecord>", xml, re.S):
        r = rec.group(0); ui = re.search(r"<DescriptorUI>(D\d+)</DescriptorUI>", r).group(1)
        name[ui] = re.search(r"<DescriptorName>\s*<String>(.*?)</String>", r, re.S).group(1)
        trees[ui] = re.findall(r"<TreeNumber>(.*?)</TreeNumber>", r)
    prefixes = [(t, MESH_AXIS[n]) for ui, n in name.items() if n in MESH_AXIS for t in trees[ui]]
    return {ui: {a for t in ts for p, a in prefixes if t == p or t.startswith(p + ".")} for ui, ts in trees.items()}


def doid_axes():
    T, cur = {}, None
    for line in open(DOID, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == "[Term]": cur = None
        elif line.startswith("id: "): cur = line[4:]; T[cur] = dict(name="", parents=[])
        elif cur and line.startswith("name: "): T[cur]["name"] = line[6:]
        elif cur and line.startswith("is_a: "): T[cur]["parents"].append(line[6:].split()[0])
    memo = {}
    def axes(t, seen=()):
        if t in memo: return memo[t]
        a = {DOID_AXIS[T[t]["name"]]} if t in T and T[t]["name"] in DOID_AXIS else set()
        for p in T.get(t, {}).get("parents", []):
            if p not in seen: a |= axes(p, seen + (t,))
        memo[t] = a; return a
    return {t: axes(t) for t in T}


def hpo_shares():
    """OMIM:/ORPHA: id -> 13-vector share of its HPO annotations in each organ branch."""
    from linking_models import HPO_BRANCH
    par, cur = collections.defaultdict(list), None
    for line in open(HP, encoding="utf-8"):
        if line.startswith("id: "): cur = line[4:].strip()
        elif line.startswith("is_a: ") and cur: par[cur].append(line[6:].split()[0])
    memo = {}
    def branch(t):
        if t in memo: return memo[t]
        out, st, seen = set(), [t], set()
        while st:
            n = st.pop()
            if n in seen: continue
            seen.add(n)
            if n in HPO_BRANCH: out.add(HPO_BRANCH[n])
            st.extend(par.get(n, []))
        memo[t] = out; return out
    ann = collections.defaultdict(list)
    for line in open(HPOA, encoding="utf-8"):
        if line.startswith("#") or line.startswith("database_id"): continue
        f = line.rstrip("\n").split("\t")
        if len(f) > 10 and f[10] == "P" and f[2] != "NOT": ann[f[0]].append(f[3])
    out = {}
    for d, hs in ann.items():
        v = np.zeros(len(AXES))
        for h in hs:
            for a in branch(h): v[AXES.index(a)] += 1
        out[d] = v / max(1, len(hs))
    return out


def build():
    X = xrefs(); mesh = mesh_tree(); doid = doid_axes(); hpo = hpo_shares(); T = read_obo()
    ids = sorted(t for t in T if t.startswith("MONDO:")); V = np.zeros((len(ids), len(SOURCES), len(AXES)), np.float32)
    have = collections.Counter()
    for i, t in enumerate(ids):
        xs = X.get(t, [])
        V[i, 0] = icd_votes([x for x in xs if x.startswith(("ICD10CM", "ICD9"))])
        for x in xs:
            s, c = x.split(":", 1)
            if s == "MESH":
                for a in mesh.get(c, ()): V[i, 1, AXES.index(a)] = 1
            elif s == "DOID":
                for a in doid.get(x, ()): V[i, 2, AXES.index(a)] = 1
        hv = [hpo[k] for k in (["OMIM:" + x.split(":")[1] for x in xs if x.startswith("OMIM:")] + ["ORPHA:" + x.split(":")[1] for x in xs if x.startswith("Orphanet:")]) if k in hpo]
        if hv: V[i, 3] = np.mean(hv, 0)
        for k, s in enumerate(SOURCES):
            if V[i, k].any(): have[s] += 1
    np.savez_compressed(P.CACHE + "organ_votes.npz", ids=np.array(ids), V=V, sources=np.array(SOURCES))
    print("concepts", len(ids), "with a vote:", dict(have))


if __name__ == "__main__":
    build()
