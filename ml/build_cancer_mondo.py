"""MONDO cancer -> the ADC label cancers it falls under, so a cancer typed with the diseases picks the ADCs approved for it.

  python3 ml/build_cancer_mondo.py   -> data/curated/competition/cancer_mondo.json
      {"terms": {MONDO id: [name, [cancers from adc_cancers.csv]]}, "aliases": {typed name, folded: MONDO id}}

Every MONDO cancer (MONDO:0004992 'cancer', lymphoma, leukemia and below, and the roots in cancer_roots.csv and below) is listed.
A term takes the cancers of its most specific roots in cancer_roots.csv (a root that is an ancestor of another matched root gives
way); a solid cancer also takes the tumour-agnostic 'HER2+ (IHC 3+) solid tumor'. An empty list is a cancer no ADC is approved for.
A 'non-human animal' term takes the human term of the same name (the linker sometimes lands on one). cancer_aliases.csv names the
cancers the disease linker misreads (폐암 -> pneumoconiosis); they are read as cancers before linking."""
import csv, json, os

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..") + os.sep
OBO = R + "data/raw_big/mondo/2026-10-07/mondo.obo"
ROOTS = R + "data/curated/competition/cancer_roots.csv"
ALIASES = R + "data/curated/competition/cancer_aliases.csv"
CANCERS = R + "data/curated/competition/adc_cancers.csv"
OUT = R + "data/curated/competition/cancer_mondo.json"
CANCER = {"MONDO:0004992", "MONDO:0005062", "MONDO:0005059"}   # cancer; lymphoma and leukemia sit outside it in MONDO
HEME = {"MONDO:0002334", "MONDO:0044881", "MONDO:0005157"}     # hematopoietic and lymphoid neoplasms: not solid
SOLID = "HER2+ (IHC 3+) solid tumor"
ANIMAL = ", non-human animal"


def fold(text):
    """how a typed name is looked up: no spaces, hyphens or case"""
    return "".join(text.split()).replace("-", "").lower()


def terms():
    T, cur = {}, None
    for line in open(OBO, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == "[Term]" or line.startswith("["): cur = None
        if line.startswith("id: MONDO:"): cur = line[4:]; T[cur] = dict(name="", parents=set(), obs=False)
        elif cur is None: continue
        elif line.startswith("name: "): T[cur]["name"] = line[6:]
        elif line.startswith("is_obsolete: true"): T[cur]["obs"] = True
        elif line.startswith("is_a: MONDO:"): T[cur]["parents"].add(line[6:].split()[0])
    return T


def build():
    T = terms(); memo = {}
    def anc(t):
        if t not in memo:
            seen, st = set(), list(T[t]["parents"]) if t in T else []
            while st:
                n = st.pop()
                if n not in seen: seen.add(n); st.extend(T[n]["parents"] if n in T else ())
            memo[t] = seen
        return memo[t]
    known = {r["cancer"] for r in csv.DictReader(open(CANCERS, encoding="utf-8"))}
    roots = {r["mondo_id"]: [c for c in r["cancers"].split(";") if c] for r in csv.DictReader(open(ROOTS, encoding="utf-8"))}
    bad = {c for cs in roots.values() for c in cs} - known
    assert not bad, f"cancers not in adc_cancers.csv: {bad}"
    assert all(r in T and not T[r]["obs"] for r in roots), "a root is missing or obsolete in MONDO"
    out = {}
    for t, d in T.items():
        if d["obs"] or not d["name"] or ANIMAL in d["name"]: continue
        up = anc(t) | {t}
        if not up & CANCER and not up & set(roots): continue
        hit = [r for r in roots if r in up]
        hit = [r for r in hit if not any(r in anc(o) for o in hit if o != r)]           # the most specific roots
        cs = {c for r in hit for c in roots[r]}
        if not up & HEME and t not in CANCER: cs.add(SOLID)                   # 'cancer' alone: solid or not is unknown
        out[t] = [d["name"], sorted(cs)]
    human = {v[0]: k for k, v in out.items()}
    for t, d in T.items():
        if not d["obs"] and d["name"].endswith(ANIMAL) and d["name"][:-len(ANIMAL)] in human: out[t] = out[human[d["name"][:-len(ANIMAL)]]]
    aliases = {fold(r["text"]): r["mondo_id"] for r in csv.DictReader(open(ALIASES, encoding="utf-8"))}
    assert all(m in out for m in aliases.values()), "an alias names no cancer"
    json.dump(dict(terms=dict(sorted(out.items())), aliases=aliases), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return out


if __name__ == "__main__":
    out = build()
    print(f"{len(out)} cancers, {sum(1 for v in out.values() if v[1] != [SOLID] and v[1])} under an approved cancer -> {os.path.relpath(OUT, R)}")
