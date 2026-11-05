"""MONDO's numbered subtypes -> their general concept, for ml/subtypes.py.

    python3 ml/build_subtypes.py [mondo.obo]   -> data/curated/disease_linking/subtype_general.json
        {subtype id: [subtype name, general id or null, general name or null]}

The general concept of a subtype is, in this order: the concept named by what is left without the number, read with its comma parts
in any order ('Pulmonary hypertension, primary, 1' -> primary pulmonary hypertension) among MONDO names and exact synonyms; the same
with trailing comma parts dropped ('Charcot-Marie-Tooth disease, axonal, type 2FF' -> Charcot-Marie-Tooth disease); else the nearest
unnumbered is_a ancestor that shares at least half its words with that text."""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import subtypes as ST

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..") + os.sep
OBO = R + "data/raw_big/mondo/2026-10-07/mondo.obo"
OUT = R + "data/curated/disease_linking/subtype_general.json"
ROOT = "MONDO:0000001"; ANIMAL = "MONDO:0005583"
SKIP = {"disease", "disorder", "syndrome", "of", "the", "and", "with", "to", "or", "due", "in", "type", "susceptibility"}


def terms(path):
    T, cur = {}, None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("["): cur = None
        if line.startswith("id: MONDO:"): cur = line[4:]; T[cur] = dict(name="", syn=[], parents=[], obs=False)
        elif cur is None: continue
        elif line.startswith("name: "): T[cur]["name"] = line[6:]
        elif line.startswith("is_obsolete: true"): T[cur]["obs"] = True
        elif line.startswith("is_a: MONDO:"): T[cur]["parents"].append(line[6:].split()[0])
        elif line.startswith("synonym: ") and " EXACT " in line:
            q = re.match(r'synonym: "(.*)" EXACT', line)
            if q: T[cur]["syn"].append(q.group(1))
    return T


def words(text): return re.findall(r"[a-z0-9]+", text.lower())


def key(text): return " ".join(sorted(words(text)))


def ancestors(T, t):
    seen, st = set(), list(T[t]["parents"])
    while st:
        n = st.pop()
        if n not in seen and n in T: seen.add(n); st += T[n]["parents"]
    return seen


def build(T):
    human = {t for t, d in T.items() if not d["obs"] and d["name"] and (t == ROOT or ROOT in ancestors(T, t)) and ANIMAL not in ancestors(T, t)}
    numbered = {t for t in human if ST.parse(T[t]["name"])}
    by_name, by_syn = {}, {}
    for t in sorted(human - numbered):
        by_name.setdefault(key(T[t]["name"]), t)
        for s in T[t]["syn"]: by_syn.setdefault(key(s), t)
    def named(text):
        k = key(text)
        return by_name.get(k) or by_syn.get(k) if k else None
    def walk(t, stem):
        want = set(words(stem)) - SKIP; level, seen = list(T[t]["parents"]), set()
        while level and want:
            hits = []
            for a in sorted(level):
                have = set(words(T[a]["name"])) - SKIP
                if a in human and a not in numbered and have and len(have & want) * 2 >= len(want | have): hits.append((-len(have & want), a))
            if hits: return min(hits)[1]
            seen.update(level); level = [p for a in level if a in T for p in T[a]["parents"] if p not in seen]
        return None
    out = {}
    for t in sorted(numbered):
        stem = ST.parse(T[t]["name"])[0]; parts = [p.strip() for p in stem.split(",")]
        g = next(filter(None, (named(", ".join(parts[:n])) for n in range(len(parts), 0, -1))), None) or walk(t, stem)
        out[t] = [T[t]["name"], g, T[g]["name"] if g else None]
    return out


if __name__ == "__main__":
    M = build(terms(sys.argv[1] if len(sys.argv) > 1 else OBO))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in M.items()) + "\n}\n")
    print(f"{len(M)} numbered subtypes, {sum(v[1] is not None for v in M.values())} with a general concept -> {OUT}")
