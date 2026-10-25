"""Training data for judges that are not Gemma (ml/scratch_judge.py): the same sources, filters and checks as ml/gemma_judge2.py,
plus the name pairs a model trained from scratch needs to learn which names mean the same disease.

    import judge_data as JD
    items, junk_val, info = JD.items(drop={"ko3"}, seed=7)       # (text, concept, organ vec, valid, None, -1, src), as gemma_judge2
    pairs = JD.pairs(drop=set(), seed=7)                        # [(text_a, text_b, concept or None, src)] same-disease name pairs

Items follow gemma_judge2 source by source (mondo_names, train_queries, external, profiles, kcd, gen_ko, gen_sym, mondo_ko, ko2,
kotypo, ko3, umls (ml/umls_build.py items, when present), junk with JUNK_COPIES after the dedupe, then the eval-text leak drop). One difference: gemma_judge2 keeps the id of a
gold concept (or relative) on an item for its valid and sym outputs; here such an item has no concept at all, because a concept id
here also trains which texts are the same disease.
Pairs (gold concepts and their relatives never appear; a pair whose text is an evaluation query is dropped):
  mondo     MONDO name with each exact synonym
  mondo_ko  reviewed Korean name with the English MONDO name, and with its Korean alternatives
  kcd       HIRA KCD Korean name with its English KCD name, when the English name's nearest MONDO concept (SapBERT, as gemma_judge2)
            is not held out
  items     every concept-bearing training text with its concept's MONDO name
  umls      UMLS synonyms (ml/umls_build.py output), when present; --drop umls leaves them out
"""
import glob, json, os, random, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
G2 = P.REPO + "data/curated/judge2/gen/"; JUNK_COPIES = 4; KCD_N = 20000
SOURCES = ["mondo_names", "train_queries", "external", "profiles", "kcd", "gen_ko", "gen_sym", "mondo_ko", "ko2", "kotypo", "ko3", "umls"]
PAIR_SOURCES = ["mondo", "mondo_ko", "kcd", "items", "umls"]
UMLS = P.REPO + "data/curated/external/umls/"                       # ml/umls_build.py output (licensed, never in the repository)
HANGUL = lambda s: any("가" <= c <= "힣" for c in s)
_C = {}


def jl(pattern, root=G2):
    out = []
    for f in sorted(glob.glob(root + pattern)):
        for line in open(f, encoding="utf-8"):
            try: out.append(json.loads(line))
            except ValueError: pass
    return out


def base():
    if not _C:
        import linking_models as LM, suggest as SG
        from build_linking_pools import read_obo
        T = read_obo(); _C.update(T=T, held=LM.gold_held(T), labels=LM.load_organ_labels()[0], prof=SG.profiles())
    return _C["T"], _C["held"], _C["labels"], _C["prof"]


def kcd_pairs(seed):
    """[(korean, english, rank)] of the KCD names whose English name's nearest MONDO concept is not held out (SapBERT, as gemma_judge2)."""
    if "kcd" in _C: return _C["kcd"]
    import torch, mondo_index as MI
    T, held, _, _ = base(); MI.link(["x"]); Z = MI._IDX; ids = Z["_ids"]; E = torch.from_numpy(Z["E"].astype(np.float32)).cuda()
    kcd = list(zip([str(x) for x in Z["ko_keys"]], [str(x) for x in Z["ko_vals"]])); random.Random(seed).shuffle(kcd)
    out = []
    for i in range(0, len(kcd), 4096):
        part = kcd[i:i + 4096]; v = torch.from_numpy(MI._embed([e for _, e in part], "cuda:0").astype(np.float32)).cuda()
        for n, ((k, e), j) in enumerate(zip(part, (v @ E.T).argmax(1).cpu().numpy())):
            if ids[j] not in held: out.append((k, e, i + n))                  # i + n: rank in the shuffled list
    MI.close(); torch.cuda.empty_cache(); _C["kcd"] = out; return out


def items(drop=frozenset(), seed=7, kcd_n=KCD_N):
    import tuning_ledger as TL
    T, held, labels, prof = base(); rng = random.Random(seed); pid = {p["id"] for p in prof}; drop = set(drop); out = []
    def add(text, t=None, valid=1.0, src="?"):
        if not text or not str(text).strip(): return
        t = t if (t is not None and t not in held and t in T) else None
        o = np.array([x in labels[t] for x in AXES], np.float32) if (t is not None and t in labels) else None
        out.append((str(text).strip(), t, o, valid, None, -1, src))
    if "mondo_names" not in drop:
        for t in labels:
            if t not in held and t in T:
                for q in [T[t]["name"]] + T[t]["syn"][:5]: add(q, t, src="mondo_names")
    if "train_queries" not in drop:
        for f in sorted(glob.glob(P.REPO + "data/curated/train_queries/review/review2_*.jsonl")):
            for x in map(json.loads, open(f)):
                if x.get("validity") == "valid" and x.get("match") is True and x["concept"] in labels and x["concept"] not in held: add(x["query"], x["concept"], src="train_queries")
    ext = P.REPO + "data/curated/external/mentions_mondo.jsonl"
    if "external" not in drop and os.path.exists(ext):
        for r in map(json.loads, open(ext)):
            if r["split"] == "train" and len(r["mondo"]) == 1 and r["mondo"][0] in labels and r["mondo"][0] not in held: add(r["mention"], r["mondo"][0], src="external")
    elif "external" not in drop: drop.add("external")
    if "profiles" not in drop:
        for p in prof:
            for k in p.get("ko", []) + p.get("ko_lay", []) + p.get("en", []) + p.get("abbr", []): add(k, p["id"], src="profiles")
            for k in p.get("symptoms_ko", [])[:3] + p.get("symptoms_en", [])[:3]: add(k, p["id"], src="profiles_sym")     # organs only, no pair
    if "kcd" not in drop:
        for k, _, r in kcd_pairs(seed):                                       # gemma_judge2: the first kcd_n of the shuffle, then the held filter
            if r < kcd_n: add(k, None, src="kcd")
    if "gen_sym" not in drop:
        for x in jl("sym_*.jsonl"):
            if x.get("id") in pid: add(x.get("text"), x["id"], src="gen_sym")
    for name, pat in (("gen_ko", "ko_*.jsonl"), ("ko2", "ko2_*.jsonl"), ("kotypo", "kotypo_*.jsonl"), ("ko3", "ko3_*.jsonl")):
        if name not in drop:
            for x in jl(pat): add(x.get("text"), x.get("id"), src=name)
    if "mondo_ko" not in drop:
        for x in map(json.loads, open(P.REPO + "data/curated/korean/mondo_ko.jsonl", encoding="utf-8")):
            if x["conf"] != "low" and x["id"] in T:
                for k in [x["ko"]] + x["alt"]: add(k, x["id"], src="mondo_ko")
    if "umls" not in drop and os.path.exists(UMLS + "items.jsonl"):      # UMLS names of concepts linked to one labelled MONDO concept
        for r in map(json.loads, open(UMLS + "items.jsonl", encoding="utf-8")): add(r["text"], r["mondo"], src="umls")
    elif "umls" not in drop: drop.add("umls")
    junk = list(dict.fromkeys(str(x.get("text", "")).strip() for x in jl("junk_*.jsonl") if str(x.get("text", "")).strip())); rng.shuffle(junk)
    junk_val = junk[: len(junk) // 10]
    for j in junk[len(junk) // 10:]: out.append((j, None, None, 0.0, None, -1, "junk"))
    out = list({(x[0], x[1], x[3]): x for x in out}.values())
    out, n_leak = TL.drop_leaks(out)
    ev = TL.eval_concepts(); n0 = len(out)
    out = [x for x in out if TL.norm(x[0]) not in ev or x[6] == "junk"]       # stricter than gemma_judge2: no evaluation text with any concept
    n_ev = n0 - len(out)
    out += [x for x in out if x[6] == "junk"] * (JUNK_COPIES - 1)
    return out, junk_val, dict(dropped_eval_text_gold=n_leak, dropped_eval_text_other=n_ev, sources_left_out=sorted(drop))


def pairs(drop=frozenset(), seed=7, items_=None):
    import tuning_ledger as TL
    T, held, labels, _ = base(); ev = TL.eval_concepts(); out = []
    def add(a, b, t, src):
        if a and b and TL.norm(a) != TL.norm(b) and TL.norm(a) not in ev and TL.norm(b) not in ev: out.append((a, b, t, src))
    if "mondo" not in drop:
        for t, x in T.items():
            if t in held or x["name"].startswith("obsolete"): continue
            for s in x["syn"]: add(x["name"], s, t, "mondo")
    if "mondo_ko" not in drop:
        for x in map(json.loads, open(P.REPO + "data/curated/korean/mondo_ko.jsonl", encoding="utf-8")):
            t = x["id"]
            if x["conf"] == "low" or t not in T or t in held: continue
            add(x["ko"], T[t]["name"], t, "mondo_ko")
            for k in x["alt"]: add(x["ko"], k, t, "mondo_ko")
    if "kcd" not in drop:
        for k, e, _ in kcd_pairs(seed): add(k, e, None, "kcd")
    if "items" not in drop and items_ is not None:
        for x in items_:
            if x[1] is not None and x[6] not in ("mondo_names", "profiles_sym"): add(x[0], T[x[1]]["name"], x[1], "items")
    if "umls" not in drop and os.path.exists(UMLS + "pairs.jsonl"):
        for r in map(json.loads, open(UMLS + "pairs.jsonl", encoding="utf-8")): add(r["a"], r["b"], r.get("mondo"), "umls")
    return out


EXTRA_PAIRS = ["entypo", "lrabr"]
SPELL = [("haem", "hem"), ("oe", "e"), ("ae", "e"), ("our", "or"), ("ise", "ize"), ("tre", "ter"), ("ph", "f")]


def typo(s, rng):
    """one plausible English misspelling: a British/American spelling swap if one applies, else a deleted, doubled, swapped or
    replaced letter (a neighbouring key), or lower case."""
    sw = [(a, b) for a, b in SPELL if a in s.lower()] + [(b, a) for a, b in SPELL[:5] if b in s.lower() and rng.random() < 0.3]
    if sw and rng.random() < 0.4:
        a, b = rng.choice(sw); i = s.lower().index(a); return s[:i] + b + s[i + len(a):]
    pos = [i for i, c in enumerate(s) if c.isalpha()]
    if len(pos) < 4: return s.lower()
    i = rng.choice(pos[1:]); op = rng.random(); near = "qwertyuiopasdfghjklzxcvbnm"
    if op < 0.3: return s[:i] + s[i + 1:]
    if op < 0.5: return s[:i] + s[i] + s[i:]
    if op < 0.75 and i + 1 < len(s): return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    k = near.find(s[i].lower()); return s[:i] + (near[max(0, k - 1)] if k > 0 else "e") + s[i + 1:]


def extra_pairs(kinds, seed=7):
    """opt-in name pairs (ml/scratch_judge.py --add-pairs), from training concepts only:
    entypo  a misspelling of an English MONDO name or synonym -> the name (up to 3 per concept)
    lrabr   an abbreviation from the SPECIALIST lexicon (LRABR) whose expansion is a MONDO name or synonym of exactly one concept -> its name"""
    import tuning_ledger as TL
    T, held, _, _ = base(); ev = TL.eval_concepts(); rng = random.Random(seed); out = []
    def add(a, b, t, src):
        if a and b and TL.norm(a) != TL.norm(b) and TL.norm(a) not in ev and TL.norm(b) not in ev: out.append((a, b, t, src))
    ok = {t: x for t, x in T.items() if t.startswith("MONDO:") and t not in held and not x["name"].startswith("obsolete")}
    if "entypo" in kinds:
        for t, x in ok.items():
            for s in rng.sample([x["name"]] + x["syn"], min(3, 1 + len(x["syn"]))):
                if not HANGUL(s): add(typo(s, rng), x["name"], t, "entypo")
    if "lrabr" in kinds:
        import linking_models as LM
        by = {}
        for t, x in ok.items():
            for n in [x["name"]] + x["syn"]: by.setdefault(TL.norm(n), set()).add(t)
        ab = {}
        for line in open(LM.LRABR, encoding="utf-8"):
            f = line.split("|")
            if len(f) > 4 and f[2] in ("acronym", "abbreviation"): ab.setdefault(f[1], set()).update(by.get(TL.norm(f[4]), ()))
        for a_, ts in ab.items():
            if len(ts) == 1: t = next(iter(ts)); add(a_, ok[t]["name"], t, "lrabr")
    return out
