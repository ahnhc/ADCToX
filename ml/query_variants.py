"""Query variants v6: everyday words, abbreviations, shorthand, spelling variants and typos that people type for a MONDO disease,
written by one Sonnet 4.6 worker and checked blind by Sonnet 5.5. Plan and rules: ml/docs/query_variants_v6.md.
From b0003 the worker's "claude-sonnet-4-6" calls go to the local Qwen server on 4090_1 (QV_WORKER_BACKEND=qwen, the default);
QV_WORKER_BACKEND=anthropic sends them to Anthropic again. The verifier always stays on Anthropic.

    ADC_RESEARCH_MODE=1 python ml/query_variants.py --build      # queue: data/curated/query_variants/queue/b####.json
    ADC_RESEARCH_MODE=1 python ml/query_variants.py --run        # worker + verifier, one batch at a time, resumable
    ADC_RESEARCH_MODE=1 python ml/query_variants.py --status
    ADC_RESEARCH_MODE=1 python ml/query_variants.py --merge      # -> accepted.jsonl (the pairs judge_data.extra_pairs "qv" reads)

Left out of the queue: gold concepts and their parents and children (LM.gold_held), non-human and obsolete concepts, concepts
without an organ label. Left out of the output: any text that is an evaluation question (TL.eval_concepts, known_eval
questions) or a name of a held concept, and any text that already is a MONDO name or synonym (the index has it).
"""
import argparse, glob, json, os, random, re, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1"); os.environ.setdefault("ADCTOX_LABELS", "v51")   # the organ labels the X models train on
import adc_paths as P

D = P.REPO + "data/curated/query_variants/"
WORKER, VERIFIER = "claude-sonnet-4-6", "claude-sonnet-5-5"
CATS = ("lay", "abbrev", "shorthand", "variant", "typo")
BATCH, NEAR = 20, 4
BACKOFF = (15, 30, 60)                                             # minutes, on a usage limit or a failed call

# worker backend: Qwen on 4090_1, reached through an ssh tunnel this script opens (port 8080 is not reachable from here, ssh is)
BACKEND = os.environ.get("QV_WORKER_BACKEND", "qwen")
QWEN_MODEL, QWEN_PORT = "qwen3.8-flash-next-iq3_s", 18080
QWEN_KEY = os.path.expanduser("~/.config/qv/qwen_key")
QWEN_SSH = ["ssh", "-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
            "-i", os.path.expanduser("~/.ssh/id_ed25519_4090_1_hyeongchanahn"),
            "-L", f"127.0.0.1:{QWEN_PORT}:127.0.0.1:8080", "hyeongchanahn@10.1.16.189"]
WORKER_AS = f"{WORKER} via {QWEN_MODEL} (4090_1)" if BACKEND == "qwen" else WORKER
_tunnel = None


def ensure_tunnel():
    """(re)open the ssh tunnel to the Qwen server; it is a child of this process and closes with it."""
    global _tunnel
    import atexit, socket
    if _tunnel is not None and _tunnel.poll() is None: return
    _tunnel = subprocess.Popen(QWEN_SSH, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    atexit.register(lambda p=_tunnel: p.poll() is None and p.terminate())
    for _ in range(30):
        if _tunnel.poll() is not None: raise RuntimeError(f"ssh tunnel to 4090_1 exited: {_tunnel.stderr.read().decode()[-300:]}")
        try: socket.create_connection(("127.0.0.1", QWEN_PORT), timeout=1).close(); return
        except OSError: time.sleep(1)
    raise RuntimeError("ssh tunnel to 4090_1 did not open")


def held_texts():
    import linking_models as LM, tuning_ledger as TL, known_eval as KE
    from build_linking_pools import read_obo
    T = read_obo(); held = LM.gold_held(T); ev = set(TL.eval_concepts())
    for qs in KE.questions().values(): ev |= {TL.norm(q["text"]) for q in qs}
    ev |= {TL.norm(n) for t in held if t in T for n in [T[t]["name"]] + T[t]["syn"]}
    return T, held, ev


def build():
    import numpy as np, linking_models as LM
    from sklearn.feature_extraction.text import TfidfVectorizer
    T, held, _ = held_texts(); labels = LM.load_organ_labels()[0]    # non-human concepts are already dropped here
    rec = {x["id"]: x for x in map(json.loads, open(P.REPO + "data/curated/concept_organs/v5/input/concepts.jsonl", encoding="utf-8"))}
    ok = [t for t in rec if t in labels and labels[t] and t not in held and t in T and not T[t]["name"].startswith("obsolete")]
    prof = {x["id"] for f in sorted(glob.glob(P.REPO + "data/curated/disease_profiles/profiles_*.jsonl")) for x in map(json.loads, open(f, encoding="utf-8"))}
    # order: profile diseases first (what people type most), then by how many vocabularies name the concept, then by id
    def xn(t): return sum(len(v) for v in rec[t].get("xrefs", {}).values())
    ok.sort(key=lambda t: (t not in prof, -xn(t), t))
    names = [T[t]["name"] for t in ok]
    V = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), sublinear_tf=True).fit(names); X = V.transform(names)
    near = {}
    for i in range(0, len(ok), 2000):                              # nearest other names: the confusable candidates the verifier sees
        S = (X[i:i + 2000] @ X.T).toarray()
        for j, row in enumerate(S):
            row[i + j] = -1; near[ok[i + j]] = [ok[k] for k in np.argsort(-row)[:NEAR]]
    sib = {}
    for t in ok:
        for p in T[t]["parents"]: sib.setdefault(p, []).append(t)
    os.makedirs(D + "queue", exist_ok=True)
    for b in range(0, len(ok), BATCH):
        items = []
        for t in ok[b:b + BATCH]:
            r = rec[t]; s = [u for p in T[t]["parents"] for u in sib.get(p, []) if u != t][:6]
            items.append(dict(id=t, name=r["name"], synonyms=r["synonyms"], related_synonyms=r.get("related_synonyms", []),
                              definition=r["definition"][:400], parents=r["parents"], siblings=[T[u]["name"] for u in s],
                              confusable=list(dict.fromkeys([p for p in T[t]["parents"] if p in T and p not in held][:1] + s[:2] + near[t]))[:NEAR + 1]))
        json.dump(dict(batch=b // BATCH, concepts=items), open(D + f"queue/b{b // BATCH:04d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(dict(n_concepts=len(ok), n_batches=(len(ok) + BATCH - 1) // BATCH, n_profile_first=len(prof & set(ok)), batch=BATCH,
                   held_out=len(held), worker=WORKER, verifier=VERIFIER), open(D + "queue/manifest.json", "w", encoding="utf-8"), indent=1)
    print(len(ok), "concepts,", (len(ok) + BATCH - 1) // BATCH, "batches")


def call(model, system, prompt):
    """one fresh, tool-less Claude Code session in an empty folder; -> (text, info). Raises on a failed call."""
    qwen = model == WORKER and BACKEND == "qwen"; env = None
    if qwen:
        ensure_tunnel(); env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env.update(ANTHROPIC_BASE_URL=f"http://127.0.0.1:{QWEN_PORT}", ANTHROPIC_AUTH_TOKEN=open(QWEN_KEY, encoding="utf-8").read().strip(),
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
                   CLAUDE_CODE_MAX_OUTPUT_TOKENS="64000",   # Qwen thinks at length; b0004 went over the 32k default
                   CLAUDE_CODE_EFFORT_LEVEL="medium")       # Strata maps effort to how long Qwen thinks; higher ran out of tokens
    wd = tempfile.mkdtemp(prefix="qv_"); t0 = time.time()
    try:
        p = subprocess.run(["claude", "-p", "--model", model, "--setting-sources", "project", "--strict-mcp-config", "--tools", "",
                            "--no-session-persistence", "--output-format", "json", "--system-prompt", system],
                           input=prompt, capture_output=True, text=True, cwd=wd, timeout=1800, env=env)
    finally: shutil.rmtree(wd, ignore_errors=True)
    try: d = json.loads(p.stdout)
    except ValueError: raise RuntimeError(f"exit {p.returncode}: {(p.stdout or p.stderr)[-400:]}")
    used = list(d.get("modelUsage", {}))
    if d.get("is_error") or p.returncode: raise RuntimeError(f"error: {str(d.get('result'))[:400]}")
    if used and used != [model]: raise SystemExit(f"model mismatch: asked {model}, used {used}")   # the worker must be Sonnet 4.6
    u = d.get("usage", {})
    return d.get("result", ""), dict(model=model, used=used, backend=QWEN_MODEL if qwen else "anthropic", sec=round(time.time() - t0, 1),
                                     cost_usd=None if qwen else d.get("total_cost_usd"),   # Claude Code prices Qwen calls at Sonnet list price
                                     in_tok=u.get("input_tokens"), out_tok=u.get("output_tokens"), cache_read=u.get("cache_read_input_tokens"))


def parse(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m: raise ValueError("no JSON object in the reply")
    return json.loads(m.group(0))


def check_gen(out, batch):
    ids = [c["id"] for c in batch["concepts"]]; bad = []
    for x in out.get("items", []):
        if x.get("id") not in ids: bad.append(f"unknown id {x.get('id')}")
        if x.get("category") not in CATS: bad.append(f"bad category {x.get('category')}")
        if not str(x.get("query", "")).strip() or len(x["query"]) > 120: bad.append(f"bad query {x.get('query')!r}")
    if not out.get("items"): bad.append("no items")
    return bad


def generate(batch, guide, log):
    prompt = guide + "\n\n## Batch\n\n" + json.dumps([{k: c[k] for k in ("id", "name", "synonyms", "related_synonyms", "definition", "parents", "siblings")}
                                                     for c in batch["concepts"]], ensure_ascii=False, indent=1)
    for k in range(2):
        text, info = call(WORKER, "You are a careful clinical terminology annotator. Reply with one JSON object only.", prompt); log(dict(step="gen", **info))
        try:
            out = parse(text); bad = check_gen(out, batch)
            if not bad: return out
        except ValueError as e: bad = [str(e)]
        prompt += "\n\nYour previous reply had these problems; reply again with the whole corrected JSON object:\n- " + "\n- ".join(bad[:20])
    raise RuntimeError("worker output failed the format check twice: " + "; ".join(bad[:5]))


def clean(out, batch, T, ev):
    """drop texts that are evaluation questions, held names, or already a MONDO name/synonym; dedupe within the batch."""
    import tuning_ledger as TL
    known = {TL.norm(n) for c in batch["concepts"] for n in [c["name"], *c["synonyms"]]}; seen, keep, drop = set(), [], []
    for x in out["items"]:
        k = TL.norm(x["query"])
        why = "eval or held text" if k in ev else "already a MONDO name" if k in known or k in NAMES else "duplicate" if (x["id"], k) in seen or not k else None
        (drop if why else keep).append(dict(x, drop=why) if why else x); seen.add((x["id"], k))
    return keep, drop


def verify(batch, items, vguide, T, log, seed):
    """blind check: the verifier sees each query and a shuffled candidate list (the concept, its parent, siblings, nearest names)."""
    rng = random.Random(seed); groups, key = [], {}
    by = {}
    for i, x in enumerate(items): by.setdefault(x["id"], []).append(i)
    for c in batch["concepts"]:
        if c["id"] not in by: continue
        cand = [c["id"]] + [u for u in c["confusable"] if u != c["id"]]; rng.shuffle(cand)
        L = "ABCDEFG"[:len(cand)]; key[c["id"]] = dict(zip(cand, L))
        groups.append(dict(candidates=[dict(letter=l, name=T[u]["name"], definition=T[u]["defn"][:160]) for l, u in zip(L, cand)],
                           queries=[dict(n=i, query=items[i]["query"], category=items[i]["category"]) for i in by[c["id"]]]))
    prompt = vguide + "\n\n## Groups\n\n" + json.dumps(groups, ensure_ascii=False, indent=1)
    for k in range(2):
        text, info = call(VERIFIER, "You are a strict clinical terminology reviewer. Reply with one JSON object only.", prompt); log(dict(step="verify", **info))
        try:
            v = {r["n"]: r for r in parse(text)["verdicts"]}
            if set(v) >= set(range(len(items))): break
            bad = f"missing verdicts for n = {sorted(set(range(len(items))) - set(v))[:30]}"
        except (ValueError, KeyError, TypeError) as e: bad = f"bad reply: {e}"
        prompt += f"\n\nYour previous reply had a problem ({bad}); reply again with every verdict."
    else: raise RuntimeError("verifier output failed twice")
    res = []
    for i, x in enumerate(items):
        r = v[i]; want = key[x["id"]][x["id"]]
        acc = r.get("pick") == want and r.get("realistic") is True and r.get("category_ok") is True
        res.append(dict(x, pick=r.get("pick"), want=want, realistic=r.get("realistic"), category_ok=r.get("category_ok"), why=r.get("why", ""), accepted=acc))
    return res


NAMES = set()


def run(limit=None):
    import tuning_ledger as TL
    T, held, ev = held_texts(); NAMES.update(TL.norm(n) for t, x in T.items() for n in [x["name"]] + x["syn"])
    guide = open(D + "GUIDE.md", encoding="utf-8").read(); vguide = open(D + "VERIFY.md", encoding="utf-8").read()
    import hashlib; guide_sha = hashlib.sha256(guide.encode()).hexdigest()[:12]   # GUIDE.md changed at b0004 (fewer typos)
    verify_sha = hashlib.sha256(vguide.encode()).hexdigest()[:12]                 # VERIFY.md changed at b0014 (general vs specific)
    os.makedirs(D + "out", exist_ok=True); logf = open(D + "runs.jsonl", "a", encoding="utf-8")
    def log(r): logf.write(json.dumps(dict(r, t=time.strftime("%Y-%m-%d %H:%M:%S"))) + "\n"); logf.flush()
    todo = [f for f in sorted(glob.glob(D + "queue/b*.json")) if not os.path.exists(D + "out/" + os.path.basename(f))]
    done = 0; fails = 0; recent = []
    for f in todo:
        if os.path.exists(D + "STOP"): print("STOP file present; stopping"); break
        if limit is not None and done >= limit: break
        batch = json.load(open(f, encoding="utf-8")); name = os.path.basename(f)
        try:
            out = generate(batch, guide, log); keep, drop = clean(out, batch, T, ev)
            res = verify(batch, keep, vguide, T, log, seed=batch["batch"]) if keep else []
        except RuntimeError as e:
            fails += 1; m = BACKOFF[min(fails, len(BACKOFF)) - 1]; log(dict(step="fail", batch=name, error=str(e)[:400], sleep_min=m))
            print(name, "failed:", str(e)[:200], f"-> sleeping {m} min", flush=True); time.sleep(60 * m); continue
        fails = 0; acc = sum(r["accepted"] for r in res)
        json.dump(dict(batch=batch["batch"], worker=WORKER_AS, verifier=VERIFIER, guide=guide_sha, verify_guide=verify_sha, items=res, dropped=drop), open(D + "out/" + name, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log(dict(step="done", batch=name, n=len(res), accepted=acc, dropped=len(drop))); done += 1
        recent = (recent + [(acc, len(res))])[-5:]; ra = sum(a for a, _ in recent) / max(1, sum(n for _, n in recent))
        print(f"{name}: {acc}/{len(res)} accepted, {len(drop)} dropped (last 5 batches {ra:.0%})", flush=True)
        if len(recent) == 5 and ra < 0.5:                         # stop rule in the plan
            open(D + "STOP", "w", encoding="utf-8").write(f"acceptance over the last 5 batches {ra:.0%} < 50% at {name}\n"); print("acceptance below 50%; stopping"); break


def status():
    q = len(glob.glob(D + "queue/b*.json")); outs = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(D + "out/b*.json"))]
    from collections import Counter
    n = Counter(); a = Counter()
    for o in outs:
        for r in o["items"]: n[r["category"]] += 1; a[r["category"]] += r["accepted"]
    print(f"batches {len(outs)}/{q}; items {sum(n.values())}, accepted {sum(a.values())} ({sum(a.values()) / max(1, sum(n.values())):.0%})")
    for c in CATS: print(f"  {c:<10} {a[c]:>6}/{n[c]:<6}")
    if os.path.exists(D + "STOP"): print("STOP:", open(D + "STOP", encoding="utf-8").read().strip())


def merge():
    out = []
    for f in sorted(glob.glob(D + "out/b*.json")):
        for r in json.load(open(f, encoding="utf-8"))["items"]:
            if r["accepted"]: out.append(dict(id=r["id"], query=r["query"], category=r["category"]))
    with open(D + "accepted.jsonl", "w", encoding="utf-8") as w:
        for r in out: w.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(len(out), "accepted pairs ->", D + "accepted.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); g = ap.add_mutually_exclusive_group(required=True)
    for k in ("build", "run", "status", "merge"): g.add_argument("--" + k, action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="--run: stop after this many batches")
    a = ap.parse_args()
    if a.build: build()
    elif a.run: run(a.limit)
    elif a.status: status()
    else: merge()
