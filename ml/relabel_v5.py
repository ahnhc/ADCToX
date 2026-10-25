"""Organ labels v5 (two tiers: primary / involved), made by GPT from data/curated/concept_organs/v5/GPT_TASK.md.
Plan: ml/docs/relabel_v5_plan.md. Rules the labeller follows: data/curated/concept_organs/GUIDE_v5.md.

    python ml/relabel_v5.py prepare [--passes 3] [--batch 25]   # evidence records and the independent label passes (Claude, before GPT)
    python ml/relabel_v5.py check  --stage pass1|...|pass5|adjudicate|audit     # which batches are missing or invalid
    python ml/relabel_v5.py vote               # after the passes: agreed concepts, adjudication batches for the rest
    python ml/relabel_v5.py audit              # after adjudication: audit batches (hierarchy conflicts, large changes, sample)
    python ml/relabel_v5.py assemble           # final labels_v5.jsonl, agreement statistics, REPORT.md

Layout (data/curated/concept_organs/v5/):
  input/concepts.jsonl          one evidence record per concept (MONDO only; HPO annotations when data/raw/hpo/phenotype.hpoa exists)
  passK/in/b_NNNN.json          pass K's batches (BATCH concepts, a different shuffle per pass)   -> passK/out/b_NNNN.jsonl
  adjudicate/in/a_NNNN.json     contested concepts with the five labels and the older label        -> adjudicate/out/a_NNNN.jsonl
  audit/in/u_NNNN.json          labels to audit                                                    -> audit/out/u_NNNN.jsonl
  labels_v5.jsonl, agreement.json, REPORT.md, DONE (written by assemble)
Scope: every human MONDO concept that has a v4 organ label, plus the gold concepts and their relatives (unmarked: the
labeller is never told which concepts are evaluation concepts; the training loader still leaves them out).
"""
import collections, glob, json, os, random, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

V5 = P.REPO + "data/curated/concept_organs/v5/"
OBO = P.REPO + "data/raw_big/mondo/2026-10-07/mondo.obo"; HPO = P.REPO + "data/raw/hpo/"
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
PASSES, BATCH, ADJ_BATCH, AUDIT_BATCH, SEED = 3, 25, 10, 10, 2081     # defaults of prepare; later steps read input/manifest.json


def layout():
    """(passes, agree): an organ's tier is settled when `agree` passes give it (all of them for 3 passes or fewer, else all but one)."""
    m = json.load(open(V5 + "input/manifest.json")); n = m["passes"]
    return n, (n if n <= 3 else n - 1)
AUDIT_SAMPLE = 0.03           # share of settled concepts audited at random


# ------------------------------------------------------------------ evidence
def parse_obo():
    """{id: dict(name, defn, exact, related, parents, locations, features, genes, xrefs, obsolete)} for MONDO terms."""
    T, cur = {}, None
    for line in open(OBO, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("["): cur = None; continue
        if line.startswith("id: MONDO:"):
            cur = line[4:].strip(); T[cur] = dict(name="", defn="", exact=[], related=[], parents=[], locations=[], features=[], genes=[], xrefs=collections.defaultdict(list), obsolete=False)
            continue
        if cur is None or not line: continue
        x = T[cur]; lab = line.split(" ! ", 1)[1].strip() if " ! " in line else ""
        if line.startswith("name: "): x["name"] = line[6:].strip()
        elif line.startswith("def: "): m = re.match(r'def: "(.*)"', line); x["defn"] = m.group(1) if m else ""
        elif line.startswith("synonym: "):
            m = re.match(r'synonym: "(.*)" (EXACT|RELATED|NARROW|BROAD)', line)
            if m: (x["exact"] if m.group(2) == "EXACT" else x["related"]).append(m.group(1))
        elif line.startswith("is_a: "): x["parents"].append(line[6:].split()[0])
        elif line.startswith("is_obsolete: true"): x["obsolete"] = True
        elif line.startswith("relationship: disease_has_location") and lab: x["locations"].append(lab)
        elif line.startswith("relationship: disease_has_feature") and lab: x["features"].append(lab)
        elif line.startswith("relationship: has_material_basis_in_germline_mutation_in") and lab: x["genes"].append(lab)
        elif line.startswith("xref: "):
            k = line.split()[1]; db = k.split(":")[0]
            if db in ("OMIM", "Orphanet", "DOID", "MESH", "NCIT", "ICD10CM", "ICD10WHO", "icd11.foundation", "GARD"): x["xrefs"][db].append(k)
    return T


def hpo_annotations():
    """{OMIM:n / Orphanet:n: [(phenotype name, frequency text, frequency 0-1 or None)]} from phenotype.hpoa when present, else {}."""
    f = HPO + "phenotype.hpoa"
    if not os.path.exists(f) or not os.path.exists(HPO + "hp.obo"): return {}
    names, cur = {}, None
    for l in open(HPO + "hp.obo", encoding="utf-8"):
        if l.startswith("id: HP:"): cur = l[4:].strip()
        elif l.startswith("name: ") and cur: names[cur] = l[6:].strip()
    terms = {"HP:0040280": ("obligate (100%)", 1.0), "HP:0040281": ("very frequent (80-99%)", 0.9), "HP:0040282": ("frequent (30-79%)", 0.55),
             "HP:0040283": ("occasional (5-29%)", 0.17), "HP:0040284": ("very rare (1-4%)", 0.025), "HP:0040285": ("excluded (0%)", 0.0)}
    out = collections.defaultdict(list)
    for l in open(f, encoding="utf-8"):
        if l.startswith("#") or l.startswith("database_id"): continue
        p = l.rstrip("\n").split("\t")
        if len(p) < 11 or p[10] != "P" or p[2] == "NOT": continue                     # phenotypic abnormalities only, not negated
        fr = p[7].strip()
        if fr in terms: txt, v = terms[fr]
        elif re.fullmatch(r"\d+/\d+", fr):
            k, n = map(int, fr.split("/")); v = k / n if n else None; txt = f"{k}/{n} patients"
        elif re.fullmatch(r"[\d.]+%", fr): v = float(fr[:-1]) / 100; txt = fr
        else: txt, v = "frequency not given", None
        if v == 0.0: continue
        out[p[0].replace("ORPHA:", "Orphanet:")].append((names.get(p[3], p[3]), txt, v))
    return out


def prepare(passes=PASSES, batch=BATCH):
    import linking_models as LM, shutil, time
    from build_linking_pools import read_obo
    T = parse_obo(); labels, _ = LM.load_organ_labels(); held = LM.gold_held(read_obo())
    scope = sorted((set(labels) | held) & {t for t, x in T.items() if not x["obsolete"]})
    kids = collections.defaultdict(list)
    for t, x in T.items():
        if not x["obsolete"]:
            for p in x["parents"]: kids[p].append(t)
    H = hpo_annotations()
    os.makedirs(V5 + "input", exist_ok=True); recs = []
    for t in scope:
        x = T[t]; par = [p for p in x["parents"] if p in T]; gp = sorted({g for p in par for g in T[p]["parents"] if g in T})
        r = dict(id=t, name=x["name"], synonyms=x["exact"][:8], related_synonyms=x["related"][:5], definition=x["defn"],
                 parents=[T[p]["name"] for p in par], grandparents=[T[g]["name"] for g in gp][:6],
                 children_count=len(kids[t]), children_sample=[T[k]["name"] for k in sorted(kids[t])][:8],
                 mondo_locations=x["locations"][:8], mondo_features=x["features"][:15], genes=x["genes"][:5],
                 xrefs={k: v[:4] for k, v in x["xrefs"].items()})
        ph = [p for db in ("OMIM", "Orphanet") for k in x["xrefs"].get(db, []) for p in H.get(k, [])]
        if ph:                                                             # most frequent first; unknown frequency last; at most 40
            best = {}
            for n, txt, v in ph:
                if n not in best or (v or -1) > (best[n][1] or -1): best[n] = (txt, v)
            ph = sorted(best.items(), key=lambda kv: -(kv[1][1] if kv[1][1] is not None else -1))[:40]
            r["hpo_phenotypes"] = [f"{n} [{txt}]" for n, (txt, v) in ph]
        recs.append(r)
    open(V5 + "input/concepts.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))
    old = sorted(glob.glob(V5 + "pass*/")) + [V5 + x + "/" for x in ("adjudicate", "audit") if os.path.isdir(V5 + x)]
    if old:                                                                 # an earlier layout: kept, never mixed with the new batches
        keep = V5 + "provenance/old_layout_" + time.strftime("%Y%m%d_%H%M%S") + "/"; os.makedirs(keep, exist_ok=True)
        for d in old: shutil.move(d, keep + os.path.basename(d.rstrip("/")))
        for f in ("settled.jsonl", "labels_v5.jsonl", "agreement.json", "DONE"):
            if os.path.exists(V5 + f): shutil.move(V5 + f, keep + f)
    for k in range(1, passes + 1):
        d = V5 + f"pass{k}/in/"; os.makedirs(d, exist_ok=True); os.makedirs(V5 + f"pass{k}/out/", exist_ok=True)
        order = list(recs); random.Random(SEED + k).shuffle(order)
        for n, s in enumerate(range(0, len(order), batch)): json.dump(order[s:s + batch], open(d + f"b_{n:04d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    v4 = {t: sorted(labels[t], key=AXES.index) for t in scope if t in labels}
    json.dump(v4, open(V5 + "input/v4_labels.json", "w"), indent=0)
    man = dict(concepts=len(recs), held_unmarked=len(held & set(scope)), with_hpo=sum("hpo_phenotypes" in r for r in recs), passes=passes,
               batch=batch, batches_per_pass=(len(recs) + batch - 1) // batch, seed=SEED)
    json.dump(man, open(V5 + "input/manifest.json", "w"), indent=1); print(json.dumps(man, indent=1))


# ------------------------------------------------------------------ outputs
def read_out(f):
    rows = []
    for l in open(f, encoding="utf-8"):
        l = l.strip()
        if not l or l.startswith("```"): continue
        try: rows.append(json.loads(l))
        except ValueError: rows.append({"_bad": l[:80]})
    return rows


def valid_label(r):
    """problems with one output line (empty list: valid)."""
    bad = []
    p, i = r.get("primary"), r.get("involved")
    if not isinstance(p, list) or not isinstance(i, list): return ["primary/involved not lists"]
    if any(a not in AXES for a in p + i): bad.append("unknown axis")
    if set(p) & set(i): bad.append("organ in both lists")
    if len(p) > 3 or len(set(p) | set(i)) > 4: bad.append("over the cap")
    if r.get("no_axis") and (p or i): bad.append("no_axis with organs")
    if not r.get("no_axis") and not p: bad.append("no primary organ and not no_axis")
    if r.get("confidence") not in ("high", "medium", "low"): bad.append("confidence")
    return bad


def check(stage, quiet=False):
    """-> (missing batches, invalid batches with reasons, rows by id)."""
    d = V5 + (f"{stage}/" if stage.startswith("pass") else f"{stage}/"); ins = sorted(glob.glob(d + "in/*.json")); missing, invalid, rows = [], {}, {}
    for f in ins:
        want = [(r.get("record") or r)["id"] for r in json.load(open(f, encoding="utf-8"))]; o = d + "out/" + os.path.basename(f)[:-5] + ".jsonl"
        if not os.path.exists(o): missing.append(os.path.basename(f)); continue
        got = read_out(o); ids = [r.get("id") for r in got]; why = []
        if ids != want: why.append(f"ids differ from input order ({len(ids)} lines for {len(want)})")
        for r in got:
            if stage == "audit" and r.get("verdict") == "ok": continue
            b = valid_label(r if stage != "audit" else r.get("corrected", {}))
            if b: why.append(f"{r.get('id')}: {', '.join(b)}")
        if why: invalid[os.path.basename(f)] = why[:5]
        else: rows.update({r["id"]: r for r in got})
    if not quiet:
        print(json.dumps(dict(stage=stage, batches=len(ins), done=len(ins) - len(missing) - len(invalid), missing=len(missing), invalid=len(invalid),
                              first_missing=missing[:10], first_invalid=dict(list(invalid.items())[:10])), indent=1))
    return missing, invalid, rows


def tiers(r):
    """13 organ states: 2 primary, 1 involved, 0 none."""
    return tuple(2 if a in r.get("primary", []) else 1 if a in r.get("involved", []) else 0 for a in AXES)


def vote():
    PASSES, AGREE = layout(); passes = []
    for k in range(1, PASSES + 1):
        m, inv, rows = check(f"pass{k}", quiet=True)
        if m or inv: raise SystemExit(f"pass{k} incomplete: {len(m)} missing, {len(inv)} invalid batches (python ml/relabel_v5.py check --stage pass{k})")
        passes.append(rows)
    recs = {r["id"]: r for r in map(json.loads, open(V5 + "input/concepts.jsonl", encoding="utf-8"))}
    v4 = json.load(open(V5 + "input/v4_labels.json")); settled, contested = {}, []
    for t in recs:
        L = [p[t] for p in passes]; st = [tiers(x) for x in L]; noax = [bool(x.get("no_axis")) for x in L]
        final, open_ = [], []
        for j in range(13):
            c = collections.Counter(s[j] for s in st); v, n = c.most_common(1)[0]
            final.append(v)
            if n < AGREE: open_.append(AXES[j])
        na = collections.Counter(noax).most_common(1)[0]
        if open_ or na[1] < AGREE: contested.append(dict(record=recs[t], labels=L, contested_organs=open_, older_label=v4.get(t)))
        else: settled[t] = dict(id=t, primary=[AXES[j] for j in range(13) if final[j] == 2], involved=[AXES[j] for j in range(13) if final[j] == 1],
                                no_axis=na[0], confidence=min((x.get("confidence") for x in L), key=["low", "medium", "high"].index), basis=L[0].get("basis", ""), how=f"{PASSES}-pass agreement")
    d = V5 + "adjudicate/"; os.makedirs(d + "in", exist_ok=True); os.makedirs(d + "out", exist_ok=True)
    for f in glob.glob(d + "in/*.json"): os.remove(f)
    random.Random(SEED).shuffle(contested)
    for n, s in enumerate(range(0, len(contested), ADJ_BATCH)): json.dump(contested[s:s + ADJ_BATCH], open(d + f"in/a_{n:04d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(V5 + "settled.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in settled.values()))
    print(json.dumps(dict(concepts=len(recs), settled=len(settled), contested=len(contested), adjudication_batches=(len(contested) + ADJ_BATCH - 1) // ADJ_BATCH), indent=1))


def merged():
    """settled + adjudicated (+ audit corrections when present) -> {id: label}."""
    L = {r["id"]: r for r in map(json.loads, open(V5 + "settled.jsonl", encoding="utf-8"))}
    m, inv, rows = check("adjudicate", quiet=True)
    if m or inv: raise SystemExit(f"adjudication incomplete: {len(m)} missing, {len(inv)} invalid batches")
    for t, r in rows.items(): L[t] = dict(r, how="adjudicated")
    if os.path.exists(V5 + "audit/in"):
        m, inv, rows = check("audit", quiet=True)
        if m or inv: raise SystemExit(f"audit incomplete: {len(m)} missing, {len(inv)} invalid batches")
        for t, r in rows.items():
            if r.get("verdict") == "corrected": L[t] = dict(r["corrected"], id=t, how="audit-corrected", audit_reason=r.get("reason", ""))
    return L


def audit():
    L = merged(); recs = {r["id"]: r for r in map(json.loads, open(V5 + "input/concepts.jsonl", encoding="utf-8"))}
    v4 = json.load(open(V5 + "input/v4_labels.json")); T = parse_obo(); flags = collections.defaultdict(list); rng = random.Random(SEED + 99)
    for t, r in L.items():
        pr = set(r.get("primary", [])); al = pr | set(r.get("involved", []))
        for p in T[t]["parents"]:                                           # a subtype keeps its parent's defining organs
            if p in L and not r.get("no_axis") and not (set(L[p].get("primary", [])) <= al) and L[p].get("primary"):
                flags[t].append(f"lacks the defining organs of its parent {T[p]['name']} ({', '.join(sorted(set(L[p]['primary']) - al))})")
        if t in v4 and len(al ^ set(v4[t])) >= 2: flags[t].append(f"differs from the older label by 2 or more organs (older: {', '.join(v4[t]) or 'none'})")
        if r.get("confidence") == "low": flags[t].append("low confidence")
        if str(r.get("how", "")).endswith("pass agreement") and rng.random() < AUDIT_SAMPLE: flags[t].append("random sample")
    items = [dict(record=recs[t], label={k: L[t][k] for k in ("primary", "involved", "no_axis", "confidence", "basis") if k in L[t]}, flags=v) for t, v in flags.items()]
    d = V5 + "audit/"; os.makedirs(d + "in", exist_ok=True); os.makedirs(d + "out", exist_ok=True)
    for f in glob.glob(d + "in/*.json"): os.remove(f)
    rng.shuffle(items)
    for n, s in enumerate(range(0, len(items), AUDIT_BATCH)): json.dump(items[s:s + AUDIT_BATCH], open(d + f"in/u_{n:04d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(dict(audited=len(items), batches=(len(items) + AUDIT_BATCH - 1) // AUDIT_BATCH, by_flag=collections.Counter(f.split(" (")[0].split(" of its")[0] for v in flags.values() for f in v).most_common(8)), indent=1))


def kappa(a, b):
    a, b = np.array(a), np.array(b); po = (a == b).mean(); pe = sum((a == v).mean() * (b == v).mean() for v in set(a) | set(b))
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0


def assemble():
    PASSES, _ = layout(); L = merged(); passes = [check(f"pass{k}", quiet=True)[2] for k in range(1, PASSES + 1)]; ids = sorted(L)
    agree = {}
    for j, a in enumerate(AXES):                                            # pass 1 vs pass 2 .. 5, organ tier agreement
        ks = [kappa([tiers(passes[0][t])[j] for t in ids], [tiers(passes[k][t])[j] for t in ids]) for k in range(1, PASSES)]
        fin = [np.mean([tiers(passes[k][t])[j] == tiers(L[t])[j] for t in ids]) for k in range(PASSES)]
        agree[a] = dict(kappa_between_passes=round(float(np.mean(ks)), 3), single_pass_vs_final=round(float(np.mean(fin)), 3))
    open(V5 + "labels_v5.jsonl", "w", encoding="utf-8").write("".join(json.dumps(dict(L[t], organs=sorted(set(L[t].get("primary", [])) | set(L[t].get("involved", [])), key=AXES.index)), ensure_ascii=False) + "\n" for t in ids))
    how = collections.Counter(L[t].get("how") for t in ids)
    st = dict(concepts=len(ids), how=dict(how), no_axis=sum(bool(L[t].get("no_axis")) for t in ids),
              primary_per_organ={a: sum(a in L[t].get("primary", []) for t in ids) for a in AXES},
              involved_per_organ={a: sum(a in L[t].get("involved", []) for t in ids) for a in AXES}, agreement=agree)
    json.dump(st, open(V5 + "agreement.json", "w"), indent=1)
    open(V5 + "DONE", "w").write("v5 labels assembled; see REPORT.md\n"); print(json.dumps(st, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "prepare":
        a = sys.argv[2:]; prepare(int(a[a.index("--passes") + 1]) if "--passes" in a else PASSES, int(a[a.index("--batch") + 1]) if "--batch" in a else BATCH)
    elif cmd == "check": check(sys.argv[sys.argv.index("--stage") + 1])
    elif cmd == "vote": vote()
    elif cmd == "audit": audit()
    elif cmd == "assemble": assemble()
    else: print(__doc__)
