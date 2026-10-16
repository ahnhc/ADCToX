"""Learned parts of disease linking: the concept -> organ model (P2) and the input validity gate (P3), and the MONDO index
that carries both to the terminal.

    CUDA_VISIBLE_DEVICES=3 python -I ml/linking_models.py organs      train + choose on gold dev, report gold test
    CUDA_VISIBLE_DEVICES=3 python -I ml/linking_models.py gate        train + choose threshold on gold dev, report gold test
    CUDA_VISIBLE_DEVICES=3 python -I ml/linking_models.py index       write ml_cache/mondo_index.npz (old one kept as .pre_v1)
    CUDA_VISIBLE_DEVICES=3 python -I ml/linking_models.py index2      add LRABR abbreviation readings + HPO phenotype block (v1 kept as .pre_v2)
    python -I ml/linking_models.py index3                             add Korean names from the HIRA KCD master (v2 kept as .pre_v3)

Concept -> organs. Training labels: Claude Haiku labels of human MONDO concepts (data/curated/concept_organs/). Batches that
were labelled by keyword scripts are excluded by a quality rule fixed before training (calibration exact-set match >= 0.9 against
the Sonnet gold), except concepts where two independent labels agree; the strict hand-labelled 'relabel' round is always used;
clinician-reviewed labels in labels/expert_*.jsonl override all of them.
No gold concept, parent or child is a training concept. Features: SapBERT embedding of the concept name, the existing crosswalk
axes, and a multi-hot of the concept's is_a ancestors. One L2 logistic regression per axis. The decision rule (learned alone, or
combined with the crosswalk) and the probability threshold are chosen on the gold dev split, then frozen for test.

Validity gate. Binary: does the typed text name a disease (valid) or not (ambiguous / non-disease / invalid)? Training data:
Haiku-written queries kept only from review batches that rejected the planted traps, NCBI Disease Corpus training mentions
(valid), MONDO names (valid), dictionary words that are not MONDO strings and random strings (not valid). Features: SapBERT
query embedding, top-1 similarity, top-1 minus top-2 concept margin, and simple character statistics. L2 logistic regression.
The gold (Sonnet-written queries) is never used for fitting, only for choosing the threshold (dev) and scoring (test).
"""
import glob, json, os, random, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import eval_linking as EL, mondo_index as MI
from build_linking_pools import read_obo
R = P.REPO + "data/curated/"; C = MI.C; OUT = EL.OUT; AXES = MI.AXES; DEV = "cuda:0"
norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def human_index(T):
    idx = np.load(C + "mondo_index.pre_v1.npz" if os.path.exists(C + "mondo_index.pre_v1.npz") else C + "mondo_index.npz", allow_pickle=True)
    ids = np.array([str(x) for x in idx["ids"]]); keep = np.array(["non-human animal" not in T[t]["name"] for t in ids])
    return idx, ids, keep


def ancestors_all(T, t):
    seen, st = set(), list(T[t]["parents"])
    while st:
        p = st.pop()
        if p in seen or p not in T: continue
        seen.add(p); st.extend(T[p]["parents"])
    return seen


# ------------------------------------------------------------------ labels
def load_organ_labels():
    man = json.load(open(R + "concept_organs/manifest.json")); cal = set(man["calibration"]); good, per = {}, {}
    for f in sorted(glob.glob(R + "concept_organs/labels/batch_*.jsonl")):
        L = [json.loads(l) for l in open(f)]; c = [set(x["organs"]) == set(man["calibration"][x["id"]]) for x in L if x["id"] in cal]
        ok = bool(c) and np.mean(c) >= 0.9
        for x in L:
            if x["id"] in cal or x.get("scope") == "unclear": continue
            per.setdefault(x["id"], []).append(frozenset(x["organs"]))
            if ok: good[x["id"]] = frozenset(x["organs"])
    labels = {t: s for t, s in good.items()}
    for t, v in per.items():                                           # two independent labels that agree
        if len(v) >= 2 and v[0] == v[1]: labels[t] = v[0]
    strict, strict_per, rq = {}, {}, {}
    for f in sorted(glob.glob(R + "concept_organs/labels/relabel_*.jsonl")):
        L = [json.loads(l) for l in open(f)]; c = [set(x["organs"]) == set(man["calibration"][x["id"]]) for x in L if x["id"] in cal]
        rq[os.path.basename(f)] = float(np.mean(c)) if c else None
        for x in L:
            if x["id"] in cal or x.get("scope") == "unclear": continue
            strict_per.setdefault(x["id"], []).append(frozenset(x["organs"])); strict[x["id"]] = frozenset(x["organs"])
    labels.update(strict)
    verified = {}
    if os.path.exists(R + "concept_organs/labels/verified_v2.jsonl"):                # second round (Haiku 5.5, majority of 2-3 votes)
        for x in map(json.loads, open(R + "concept_organs/labels/verified_v2.jsonl")): verified[x["id"]] = frozenset(x["organs"])
    labels.update(verified)
    filled = {}
    if os.path.exists(R + "concept_organs/labels/verified_v3.jsonl"):                # third round: every other human concept, v3 rules
        for x in map(json.loads, open(R + "concept_organs/labels/verified_v3.jsonl")): filled[x["id"]] = frozenset(x["organs"])
    labels.update(filled)
    reviewed = {}
    if os.path.exists(R + "concept_organs/labels/verified_v4.jsonl"):                # Opus review of every training label (2026-10-17)
        for x in map(json.loads, open(R + "concept_organs/labels/verified_v4.jsonl")):
            if x.get("scope") != "unclear": reviewed[x["id"]] = frozenset(x["organs"])
    labels.update(reviewed)
    expert = {}
    for f in sorted(glob.glob(R + "concept_organs/labels/expert_*.jsonl")):          # human (clinician) review: always wins
        for x in map(json.loads, open(f)):
            if x.get("scope") != "unclear": expert[x["id"]] = frozenset(x["organs"])
    labels.update(expert)
    nonhuman = _nonhuman(labels)                                                   # 215 animal concepts had labels (2026-10-17 review)
    for t in nonhuman: labels.pop(t, None)
    agree = [v[0] == v[1] for v in strict_per.values() if len(v) >= 2]
    stats = dict(n_labels=len(labels), n_strict=len(strict), n_verified=len(verified), n_filled=len(filled), n_reviewed=len(reviewed), n_expert=len(expert), n_nonhuman_dropped=len(nonhuman), relabel_calibration_exact=rq, relabel_overlap_exact=float(np.mean(agree)) if agree else None, n_relabel_overlap=len(agree))
    return labels, stats


# ------------------------------------------------------------------ concept features
def concept_features(T, idx, ids, concepts, anc_vocab):
    first = {}
    for j, t in enumerate(ids):
        if t not in first: first[t] = j
    E = idx["E"].astype(np.float32)[[first[t] for t in concepts]]; Ax = idx["axes"][[first[t] for t in concepts]].astype(np.float32)
    A = np.zeros((len(concepts), len(anc_vocab)), np.float32); av = {a: i for i, a in enumerate(anc_vocab)}
    for i, t in enumerate(concepts):
        for a in ancestors_all(T, t) | {t}:
            if a in av: A[i, av[a]] = 1
    V = vote_features(T, concepts)
    return np.c_[E, Ax * 3.0, A] if V is None else np.c_[E, Ax * 3.0, A, V * VOTES_W]


VOTES_W = 0.3               # organ votes from ICD / MeSH / DOID / HPO (ml/organ_votes.py), scaled like the crosswalk; ADC_ORGAN_VOTES=0 turns them off
_VOTES = {}


def vote_features(T, concepts):
    """per concept: its own votes (4 sources x 13 axes) and the largest vote among its direct parents; None without the votes file."""
    if os.environ.get("ADC_ORGAN_VOTES") == "0" or not os.path.exists(C + "organ_votes.npz"): return None
    if not _VOTES:
        d = np.load(C + "organ_votes.npz"); _VOTES.update(zip([str(x) for x in d["ids"]], d["V"].reshape(len(d["ids"]), -1)))
    z = np.zeros(next(iter(_VOTES.values())).shape, np.float32)
    own = np.stack([_VOTES.get(t, z) for t in concepts])
    par = np.stack([np.max([_VOTES.get(p, z) for p in T.get(t, {}).get("parents", [])] or [z], 0) for t in concepts])
    return np.c_[own, par]


def _nonhuman(labels):
    """labelled concepts that are animal diseases (MONDO's non-human branch, or a species in the name): not training concepts."""
    import re
    from build_linking_pools import read_obo, OBO
    try:
        import suggest as SG; nh = SG.nonhuman_ids(OBO); animal = SG.ANIMAL
    except Exception:
        nh = set(); animal = re.compile(r"\b(cattle|dog|horse|sheep|goat|pig|swine|chicken|poultry|rabbit|cervid|bovine|canine|feline|equine|medaka|zebrafish|non-human)\b")
    T = read_obo()
    return {t for t in labels if t in nh or (t in T and animal.search(T[t]["name"]))}


def gold_held(T):
    """gold concepts plus their parents and children: never training concepts (the gold is for evaluation only)."""
    held = {c for g in map(json.loads, open(EL.D + "gold_v0.jsonl")) for c in g["concepts"]}; children = {}
    for t, e in T.items():
        for p in e.get("parents", []): children.setdefault(p, set()).add(t)
    return held | {p for c in held for p in T.get(c, {}).get("parents", [])} | {k for c in held for k in children.get(c, ())}


def organ_model():
    from sklearn.linear_model import LogisticRegression
    T = read_obo(); idx, ids, keep = human_index(T); labels, stats = load_organ_labels()
    held = gold_held(T); stats["n_dropped_gold_related"] = len(set(labels) & held)
    concepts = sorted(set(labels) - held); from collections import Counter
    cnt = Counter(a for t in dict.fromkeys(ids[keep]) for a in ancestors_all(T, t)); anc_vocab = sorted(a for a, n in cnt.items() if n >= 20)
    X = concept_features(T, idx, ids, concepts, anc_vocab); Y = np.array([[a in labels[t] for a in AXES] for t in concepts], np.int64)
    models = []
    for k in range(len(AXES)):
        if Y[:, k].sum() < 3: models.append(None); continue
        m = LogisticRegression(C=0.5, max_iter=3000, class_weight=None); m.fit(X, Y[:, k]); models.append(m)
    return dict(models=models, anc_vocab=anc_vocab, stats=stats, T=T, idx=idx, ids=ids, keep=keep)


def predict_organs(M, concepts):
    X = concept_features(M["T"], M["idx"], M["ids"], concepts, M["anc_vocab"])
    return np.stack([m.predict_proba(X)[:, 1] if m is not None else np.zeros(len(concepts)) for m in M["models"]], 1)


def cmd_organs():
    M = organ_model(); Q = json.load(open(EL.D + "raw/queries_v0.json")); G = {g["qid"]: g for g in map(json.loads, open(EL.D + "gold_v0.jsonl"))}
    gold = [dict(G[q["qid"]], category=q["category"]) for q in Q]; groups = [q["group"] or q["qid"] for q in Q]
    split = [EL.split_of(g) for g in groups]; dev = [i for i, s in enumerate(split) if s == "dev"]; test = [i for i, s in enumerate(split) if s == "test"]
    S = json.load(open(EL.D + "raw/system_outputs_v0.json")); old = S["axes_of"]
    linked = sorted({r["sapbert_h"][0][0] for r in S["per"]} | {r["sapbert"][0][0] for r in S["per"]}); P = dict(zip(linked, predict_organs(M, linked)))
    def run(rule, th):
        out = []
        for r in S["per"]:
            t, s = r["sapbert_h"][0]
            if s < 0.75: out.append((None, [])); continue
            learned = {AXES[k] for k in np.where(P[t] >= th)[0]}; cw = set(old.get(t, []))
            organs = learned if rule == "learned" else (learned | cw) if rule == "union" else ({AXES[k] for k in np.where(P[t] >= th)[0]} | {a for a in cw if P[t][AXES.index(a)] >= th / 3}) if rule == "hybrid" else cw
            out.append((t, sorted(organs)))
        return out
    cands = [("crosswalk", 0.5)] + [(r, th) for r in ("learned", "union", "hybrid") for th in np.arange(0.2, 0.75, 0.05)]
    scored = [(EL.metrics(run(r, th), gold, dev)["macro_f1"], r, float(th)) for r, th in cands]; best = max(scored)
    res = dict(label_stats=M["stats"], n_anc_features=len(M["anc_vocab"]), chosen=dict(rule=best[1], threshold=best[2], dev_macro_f1=best[0]),
               dev={r: max(s for s, rr, _ in scored if rr == r) for r in ("crosswalk", "learned", "union", "hybrid")},
               test_crosswalk=EL.metrics(run("crosswalk", 0.5), gold, test), test_chosen=EL.metrics(run(best[1], best[2]), gold, test),
               paired_test=EL.boot(run(best[1], best[2]), run("crosswalk", 0.5), gold, test, groups))
    json.dump(res, open(OUT + "concept_organs_v1.json", "w"), indent=1, default=float)
    print(json.dumps({k: v for k, v in res.items() if not k.startswith("test_")}, indent=1, default=float))
    print("test crosswalk F1 %.3f  chosen F1 %.3f" % (res["test_crosswalk"]["macro_f1"], res["test_chosen"]["macro_f1"]))
    return M, best


# ------------------------------------------------------------------ gate
def gate_features(texts, idx_E, ids, nonhuman_mask):
    """the same features mondo_index.link() computes at run time (MI.gate_inputs), here with non-human rows masked out."""
    import torch
    texts = list(texts); Q = MI._embed(texts, DEV).astype(np.float32); Et = torch.from_numpy(idx_E).to(DEV); V, J = [], []
    for i in range(0, len(texts), 2048):
        with torch.no_grad():
            S = torch.from_numpy(Q[i:i + 2048]).to(DEV) @ Et.T
            if nonhuman_mask is not None: S[:, torch.from_numpy(nonhuman_mask).to(DEV)] = -1
            v, j = S.topk(64, dim=1)
        V.append(v.cpu().numpy()); J.append(j.cpu().numpy())
    return MI.gate_inputs(texts, Q, np.concatenate(V), np.concatenate(J), list(ids))


def gate_training_set():
    rng = random.Random(5); T = read_obo(); pos, neg = [], []
    rm = json.load(open(R + "train_queries/review_manifest.json")); traps = rm["traps"]; gens = {}
    for k in range(5):
        for i, x in enumerate(json.loads(l) for l in open(R + f"train_queries/gen/gen_{k}.jsonl")): gens[f"g{k}_{i:03d}"] = x
    review_ok = {}
    for f in sorted(glob.glob(R + "train_queries/review/review_*.jsonl")):
        L = [json.loads(l) for l in open(f)]; tr = [x for x in L if x["rid"] in traps]
        trap_reject = np.mean([x["match"] is False for x in tr]) if tr else 0
        review_ok[os.path.basename(f)] = float(trap_reject)
        if trap_reject < 0.8: continue
        for x in L:
            if x["rid"] in traps or x["rid"] not in gens: continue
            (pos if x["validity"] == "valid" else neg).append(gens[x["rid"]]["query"])
    ncbi = [json.loads(l) for l in open(R + "external/ncbi_disease_mondo.jsonl")]
    pos += rng.sample(sorted({r["mention"] for r in ncbi if r["split"] == "train"}), 1500)
    names = sorted({T[t]["name"] for t in T if t.startswith("MONDO:") and T[t]["name"] and "non-human" not in T[t]["name"]}); pos += rng.sample(names, 1500)
    mondo_norm = {norm(T[t]["name"]) for t in T if t.startswith("MONDO:")} | {norm(s) for t in T if t.startswith("MONDO:") for s in T[t]["syn"]}
    words = [w.strip() for w in open("/usr/share/dict/american-english") if w.strip().isalpha() and "'" not in w and norm(w) not in mondo_norm]
    neg += rng.sample(words, 2000)
    for _ in range(600):
        n = rng.randint(2, 12); neg.append("".join(rng.choice("abcdefghijklmnopqrstuvwxyz      ") for _ in range(n)).strip() or "x")
    neg += ["none", "n/a", "na", "nil", "unknown", "nothing", "no", "test", "asdf", "qwerty", "-", "?", "idk", "same as above", "see notes"]
    return pos, neg, review_ok


def cmd_gate(fit_only=False):
    from sklearn.linear_model import LogisticRegression
    T = read_obo(); idx, ids, keep = human_index(T); E = idx["E"].astype(np.float32); nh = ~keep
    pos, neg, review_ok = gate_training_set()
    X = gate_features(pos + neg, E, ids, nh); y = np.r_[np.ones(len(pos)), np.zeros(len(neg))]
    mu, sd = X.mean(0), X.std(0) + 1e-6; m = LogisticRegression(C=0.2, max_iter=5000, class_weight="balanced").fit((X - mu) / sd, y)
    gate = dict(w=m.coef_[0].astype(np.float32), b=np.float32(m.intercept_[0]), mu=mu.astype(np.float32), sd=sd.astype(np.float32))
    Q = json.load(open(EL.D + "raw/queries_v0.json")); G = {g["qid"]: g for g in map(json.loads, open(EL.D + "gold_v0.jsonl"))}
    gold = [G[q["qid"]] for q in Q]; groups = [q["group"] or q["qid"] for q in Q]; split = [EL.split_of(g) for g in groups]
    Xg = gate_features([q["query"] for q in Q], E, ids, nh); p = 1 / (1 + np.exp(-(((Xg - mu) / sd) @ gate["w"] + gate["b"])))
    def rates(ix, th):
        v = [i for i in ix if gold[i]["validity"] == "valid"]; inv = [i for i in ix if gold[i]["validity"] == "invalid"]; amb = [i for i in ix if gold[i]["validity"] in ("ambiguous", "non_disease")]
        return dict(valid_pass=float(np.mean(p[v] >= th)), invalid_pass=float(np.mean(p[inv] >= th)), ambiguous_or_nondisease_pass=float(np.mean(p[amb] >= th)))
    dev = [i for i, s in enumerate(split) if s == "dev"]; test = [i for i, s in enumerate(split) if s == "test"]
    grid = np.arange(0.05, 0.96, 0.01); ok = [th for th in grid if rates(dev, th)["invalid_pass"] <= 0.05]
    th = float(max(ok, key=lambda t: (rates(dev, t)["valid_pass"], -t))) if ok else 0.5
    from sklearn.metrics import roc_auc_score
    vt = [i for i in test if gold[i]["validity"] in ("valid", "invalid", "ambiguous", "non_disease")]
    res = dict(n_train=dict(pos=len(pos), neg=len(neg)), review_trap_rejection=review_ok, threshold=th, dev=rates(dev, th), test=rates(test, th),
               test_auroc_valid_vs_rest=float(roc_auc_score([gold[i]["validity"] == "valid" for i in vt], p[vt])))
    gate["threshold"] = np.float32(th)
    json.dump(res, open(OUT + "gate_v1.json", "w"), indent=1); print(json.dumps(res, indent=1))
    np.savez(C + "gate_v1.npz", **gate); return gate


# ------------------------------------------------------------------ index
def cmd_index():
    T = read_obo(); M, best = cmd_organs(); src = C + "mondo_index.npz"
    if not os.path.exists(C + "mondo_index.pre_v1.npz"): os.rename(src, C + "mondo_index.pre_v1.npz")
    idx, ids, keep = human_index(T); concepts = list(dict.fromkeys(ids[keep])); P = dict(zip(concepts, predict_organs(M, concepts)))
    rule, th = best[1], best[2]; old_ax = {}
    for t, a in zip(ids, idx["axes"]): old_ax.setdefault(t, a)
    axes = []
    for t in ids[keep]:
        p = P[t]; cw = old_ax[t] > 0
        a = (p >= th) if rule == "learned" else (p >= th) | cw if rule == "union" else (p >= th) | (cw & (p >= th / 3)) if rule == "hybrid" else cw
        axes.append(a.astype(np.float32))
    g = dict(np.load(C + "gate_v1.npz"))
    np.savez(src, E=idx["E"][keep], ids=ids[keep].astype(str), names=np.array([str(x) for x in idx["names"]])[keep].astype(str), axes=np.stack(axes),
             gate_w=g["w"], gate_b=g["b"], gate_mu=g["mu"], gate_sd=g["sd"], gate_threshold=g["threshold"], version=np.array("v1"))
    print("index v1:", int(keep.sum()), "rows (dropped", int((~keep).sum()), "non-human rows); organ rule", rule, th)




# ------------------------------------------------------------------ index v2: abbreviations (LRABR) + phenotypes (HPO)
MONDO_OBO = P.REPO + "data/raw_big/mondo/2026-10-07/mondo.obo"
LRABR = P.REPO + "data/raw/specialist_lrabr/LRABR"; HPO = P.REPO + "data/raw/hpo/hp.obo"
ABBR_SIM = 0.92             # an expansion counts only if it IS a MONDO disease name/synonym (near-exact SapBERT match)
HPO_BRANCH = {"HP:0000707": "neurologic", "HP:0001626": "cardiovascular", "HP:0002086": "pulmonary", "HP:0000478": "ocular",
              "HP:0000598": "otologic", "HP:0025031": "gastrointestinal", "HP:0001392": "hepatic", "HP:0000077": "renal",
              "HP:0001574": "dermatologic", "HP:0001871": "haematologic", "HP:0002715": "infectious_immune", "HP:0000818": "metabolic_endocrine",
              "HP:0001939": "metabolic_endocrine", "HP:0033127": "musculoskeletal", "HP:0040064": "musculoskeletal"}


def _embed_many(strs):
    import torch
    return MI._embed(list(strs), DEV if torch.cuda.is_available() else "cpu").astype(np.float32)


def mention_counts():
    """MONDO concept -> number of disease mentions in MedMentions st21pv (UMLS) + NCBI Disease (MeSH/OMIM), via MONDO xrefs."""
    import gzip
    from collections import Counter
    x = {}
    cur = None
    for line in open(MONDO_OBO, encoding="utf-8"):
        if line.startswith("id: "): cur = line[4:].strip()
        elif line.startswith("xref: ") and cur and cur.startswith("MONDO:"):
            k = line[6:].split()[0]
            if k.startswith(("UMLS:", "MESH:", "OMIM:")): x.setdefault(k, set()).add(cur)
    n = Counter()
    mm = P.REPO + "data/raw/medmentions/st21pv_corpus_pubtator.txt.gz"
    if os.path.exists(mm):
        for line in gzip.open(mm, "rt", encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) == 6:
                for t in x.get(p[5] if p[5].startswith("UMLS:") else "UMLS:" + p[5], ()): n[t] += 1
    for r in map(json.loads, open(R + "external/ncbi_disease_mondo.jsonl")):
        for t in r["mondo"]: n[t] += 1
    return n


def abbreviation_table(ids, E, T):
    """abbreviation (lower case) -> ';'-joined MONDO ids its LRABR expansions name, most established concepts first."""
    import torch
    pairs = {}
    for line in open(LRABR, encoding="utf-8"):
        p = line.rstrip("\n").split("|")
        if len(p) < 5 or p[2] not in ("acronym", "abbreviation") or not MI.ABBREV.match(p[1]): continue
        pairs.setdefault(p[1].lower(), set()).add(p[4])
    team = R + "abbreviations/team.tsv"                                 # abbreviations teammates added (ml/team_sheets.py abbrev)
    if os.path.exists(team):
        for line in open(team, encoding="utf-8"):
            if "\t" in line: a, e = line.rstrip("\n").split("\t", 1); pairs.setdefault(a.strip().lower(), set()).add(e.strip())
    exps = sorted({e for v in pairs.values() for e in v}); print("LRABR abbreviations", len(pairs), "expansions", len(exps), flush=True)
    Et = torch.from_numpy(E).to(DEV); best = {}
    for i in range(0, len(exps), 4096):
        Q = torch.from_numpy(_embed_many(exps[i:i + 4096])).to(DEV)
        with torch.no_grad(): v, j = (Q @ Et.T).max(1)
        for e, vv, jj in zip(exps[i:i + 4096], v.tolist(), j.tolist()):
            if vv >= ABBR_SIM: best[e] = ids[jj]
    freq = mention_counts()
    rank = lambda t: (-freq.get(t, 0), -len(T[t]["syn"]) if t in T else 0, t)     # most often mentioned in PubMed corpora first
    table = {}
    for a, es in pairs.items():
        cs = sorted({best[e] for e in es if e in best}, key=rank)[:6]
        if cs: table[a] = ";".join(cs)
    print("abbreviations with MONDO readings", len(table), "| asd ->", table.get("asd"), flush=True)
    return table


def hpo_block():
    T, cur = {}, None
    for line in open(HPO, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == "[Term]": cur = None; continue
        if line.startswith("[") or not line: continue
        if line.startswith("id: "): cur = line[4:].strip(); T[cur] = dict(name="", syn=[], parents=[], obs=False)
        elif cur is None: continue
        elif line.startswith("name: "): T[cur]["name"] = line[6:].strip()
        elif line.startswith("is_obsolete: true"): T[cur]["obs"] = True
        elif line.startswith("synonym: ") and " EXACT " in line: q = re.match(r'synonym: "(.*)" EXACT', line); T[cur]["syn"].append(q.group(1)) if q else None
        elif line.startswith("is_a: "): T[cur]["parents"].append(line[6:].split()[0])
    def anc(t):
        seen, st = set(), list(T[t]["parents"])
        while st:
            p = st.pop()
            if p in seen or p not in T: continue
            seen.add(p); st.extend(T[p]["parents"])
        return seen
    strs, hid, names, axes = [], [], [], []
    for t, e in T.items():
        if e["obs"] or not e["name"]: continue
        a = anc(t) | {t}
        if "HP:0000118" not in a: continue                           # phenotypic abnormality only
        v = np.zeros(len(AXES), np.float32)
        for b, ax in HPO_BRANCH.items():
            if b in a: v[AXES.index(ax)] = 1
        # terms outside every organ branch stay, so 'fatigue' finds Fatigue (no organ) rather than a wrong neighbour
        for s in [e["name"]] + e["syn"]: strs.append(s); hid.append(t); names.append(e["name"]); axes.append(v)
    print("HPO strings", len(strs), "terms", len(set(hid)), flush=True)
    return _embed_many(strs).astype(np.float16), np.array(hid), np.array(names), np.stack(axes)


def cmd_index_v2():
    """adds the abbreviation table and the HPO phenotype block to the current (v1) index; v1 is kept as .pre_v2."""
    T = read_obo(); src = C + "mondo_index.npz"; z = dict(np.load(src, allow_pickle=False)); ids = [str(x) for x in z["ids"]]
    if not os.path.exists(C + "mondo_index.pre_v2.npz"):
        import shutil; shutil.copy2(src, C + "mondo_index.pre_v2.npz")
    table = abbreviation_table(ids, z["E"].astype(np.float32), T)
    hpE, hpid, hpn, hpax = hpo_block()
    z.update(abbr_keys=np.array(sorted(table)), abbr_vals=np.array([table[k] for k in sorted(table)]), hp_E=hpE, hp_ids=hpid, hp_names=hpn, hp_axes=hpax, version=np.array("v2"))
    np.savez(src, **z); print("index v2 written")


# ------------------------------------------------------------------ index v3: Korean names (HIRA KCD master)
KCD = P.REPO + "data/raw/kcd/hira_sangbyeong_master_2025.9_utf8.csv"

def korean_table():
    """normalised Korean name -> (English name, code length; 0 = curated everyday word). Korean-medicine-only and U codes are left out; '상세불명의 X' / '기타 X' / 'X(진성)'
    also answer to X; a name shared by several codes takes the shortest (most general) code. English 'Other' / 'Unspecified'
    qualifiers and code references are dropped so the linker sees the disease words."""
    import csv
    rows = [r for r in csv.DictReader(open(KCD, encoding="utf-8")) if r["양한방구분"] != "한방" and not r["상병기호"].startswith("U") and r["영문명"]]
    def clean(e):
        e = re.sub(r"\([^)]*[A-Z][0-9][^)]*\)|\[[^\]]*\]", "", e).replace("’", "'").strip()
        e = re.sub(r"^(Other|Unspecified)\s+", "", e, flags=re.I); e = re.sub(r",?\s*(unspecified|NOS)\.?$", "", e, flags=re.I)
        return e.strip(" ,.")
    table = {}
    for r in sorted(rows, key=lambda r: (len(r["상병기호"]), r["상병기호"])):
        k = MI._ko_norm(r["한글명"]); keys = {k}
        for p in ("상세불명의", "기타"):
            if k.startswith(p): keys.add(k[len(p):])
        if k.endswith("(진성)"): keys.add(k[:-4])
        for x in keys:
            if len(x) >= 2: table.setdefault(x, (clean(r["영문명"]), len(r["상병기호"])))
    for line in open(R + "korean/lay_aliases.tsv", encoding="utf-8"):     # everyday words win over formal KCD names
        if line.strip() and not line.startswith("#"):
            k, e = line.rstrip("\n").split("\t"); table[MI._ko_norm(k)] = (e, 0)
    return table


def cmd_index_v3():
    """adds the Korean name table to the current (v2) index; v2 is kept as .pre_v3."""
    src = C + "mondo_index.npz"; z = dict(np.load(src, allow_pickle=False))
    if not os.path.exists(C + "mondo_index.pre_v3.npz"):
        import shutil; shutil.copy2(src, C + "mondo_index.pre_v3.npz")
    t = korean_table(); k = sorted(t)
    z.update(ko_keys=np.array(k), ko_vals=np.array([t[x][0] for x in k]), ko_rank=np.array([t[x][1] for x in k], np.int8), version=np.array("v3")); np.savez(src, **z)
    print("index v3 written:", len(k), "Korean names")


if __name__ == "__main__":
    {"organs": cmd_organs, "gate": cmd_gate, "index": cmd_index, "index2": cmd_index_v2, "index3": cmd_index_v3}[sys.argv[1]]()
