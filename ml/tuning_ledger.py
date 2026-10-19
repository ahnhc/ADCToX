"""Tuning ledger: which data and settings each Gemma judge training run used, and what it scored.

    python ml/tuning_ledger.py              # render ml/docs/tuning_log.md from the run cards
    python ml/tuning_ledger.py --manifest   # print the current data manifest (what a run started now would read)

A run card is ml/results/tuning/<tag>.json. ml/gemma_judge2.py writes one per run: stage and note (--stage, --note), git
commit and whether the tree was dirty, the data manifest (rows and sha256 of every file the trainer reads), arguments, item
counts per source and per output, epoch losses, the chosen epoch, calibration, the internal dev results, and the pre-training
checks. ml/bench_judge.py adds the benchmark scores of the model to its card. The log shows, per stage, what changed from the
run before (data files, arguments) and the scores, so every step of the tuning can be traced back to its data.
"""
import glob, hashlib, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P

CARDS = P.REPO + "ml/results/tuning/"
LOG = P.REPO + "ml/docs/tuning_log.md"
C = "data/curated/"
TRAIN_DATA = {                                                    # group -> globs (repo-relative) the trainer reads
    "organ_labels": [C + "concept_organs/manifest.json", C + "concept_organs/labels/*.jsonl"],
    "train_queries": [C + "train_queries/review/review2_*.jsonl", C + "external/mentions_mondo.jsonl"],
    "profiles": [C + "disease_profiles/profiles_*.jsonl"],
    "gen_ko": [C + "judge2/gen/ko_*.jsonl"],
    "gen_sym": [C + "judge2/gen/sym_*.jsonl"],
    "gen_junk": [C + "judge2/gen/junk_*.jsonl"],
    "mondo_ko": [C + "korean/mondo_ko.jsonl"],
    "gen_ko2": [C + "judge2/gen/ko2_*.jsonl"],
    "gen_kotypo": [C + "judge2/gen/kotypo_*.jsonl"],
    "gen_ko3": [C + "judge2/gen/ko3_*.jsonl"],
    "umls": [C + "external/umls/manifest.json", C + "external/umls/pairs.jsonl", C + "external/umls/items.jsonl"],   # licensed, local only
}
EVAL_DATA = {                                                     # fixed evaluation sets: never training text
    "gold": [C + "disease_linking/gold_v0.jsonl", C + "disease_linking/raw/queries_v0.json"],
    "gold_ko": [C + "judge2/gen/koeval_*.jsonl"],
    "symptom_eval": [C + "disease_profiles/symptom_eval_v0.jsonl"],
}
HANGUL = re.compile("[가-힣]")


def _sha(path, big=False):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()[:16]


def _rows(path):
    if not path.endswith(".jsonl"): return None
    return sum(1 for l in open(path, encoding="utf-8") if l.strip())


def manifest(groups=TRAIN_DATA, cache=None):
    """-> {group: {files: {path: [rows, sha]}, rows, sha}} plus the MONDO index and ontology the run read."""
    out = {}
    for g, pats in groups.items():
        files = sorted({f for p in pats for f in glob.glob(P.REPO + p) if not os.path.basename(f).startswith("koeval_") or g == "gold_ko"})
        fs = {os.path.relpath(f, P.REPO): [_rows(f), _sha(f)] for f in files}
        out[g] = dict(files=fs, rows=sum(r for r, _ in fs.values() if r), sha=hashlib.sha256(json.dumps(fs, sort_keys=True).encode()).hexdigest()[:16])
    if cache is not None:
        idx = os.path.join(cache, "mondo_index.npz")
        if os.path.exists(idx): out["mondo_index"] = dict(path=idx, sha=_sha(idx), bytes=os.path.getsize(idx))
        from build_linking_pools import OBO
        out["mondo_obo"] = dict(path=os.path.relpath(OBO, P.REPO), sha=_sha(OBO))
    return out


def git_state():
    run = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True, cwd=P.REPO).stdout.strip()
    dirty = [l[3:] for l in run("status", "--porcelain").splitlines() if l[3:].startswith(("ml/", "data/curated/"))]
    return dict(commit=run("rev-parse", "--short", "HEAD"), dirty=dirty[:50], n_dirty=len(dirty))


def norm(t): return re.sub(r"[\s\W_]+", "", str(t).lower())


def eval_concepts():
    """-> {normalised evaluation text: its gold concepts} for the gold queries (English and Korean) and the symptom queries."""
    ev = {}
    Q = json.load(open(P.REPO + C + "disease_linking/raw/queries_v0.json")); G = {x["qid"]: x for x in map(json.loads, open(P.REPO + C + "disease_linking/gold_v0.jsonl"))}
    ko = {}
    for f in glob.glob(P.REPO + C + "judge2/gen/koeval_*.jsonl"):
        for l in open(f, encoding="utf-8"):
            try: x = json.loads(l); ko[x["qid"]] = x["query_ko"]
            except (ValueError, KeyError): pass
    for q in Q:
        for t in (q["query"], ko.get(q["qid"])):
            if t: ev.setdefault(norm(t), set()).update(G[q["qid"]]["concepts"])
    for l in open(P.REPO + C + "disease_profiles/symptom_eval_v0.jsonl", encoding="utf-8"):
        if l.strip(): x = json.loads(l); ev.setdefault(norm(x["query"]), set()).update([x["target"], *x.get("also_ok", [])])
    ev.pop("", None)
    return ev


def drop_leaks(items):
    """remove training items whose text is an evaluation query and whose concept is that query's gold concept (profile names
    of gold concepts trained the valid and sym outputs before 2026-10-17). -> (kept items, n dropped)"""
    ev = eval_concepts(); keep = [x for x in items if not (x[1] is not None and x[1] in ev.get(norm(x[0]), ()))]
    return keep, len(items) - len(keep)


def checks(items, outputs_of):
    """Pre-training checks on the trainer's final item list. items: (text, concept, organ vec, valid, align vec, sym class);
    outputs_of(item) -> the outputs it trains. Returns (report, problems); a problem stops the run."""
    rep, bad = {}, []
    # language of the generated symptom sentences
    n = 0
    for f in sorted(glob.glob(P.REPO + C + "judge2/gen/sym_*.jsonl")):
        for l in open(f, encoding="utf-8"):
            if l.strip():
                x = json.loads(l); n += (x.get("lang") == "en") == bool(HANGUL.search(x.get("text", "")))
    rep["sym_language_mismatch"] = n
    if n: bad.append(f"{n} symptom sentences whose text is not in their lang")
    # overlap with the evaluation texts, per output. Same text with the gold concept = leak (stops the run); same text with
    # another concept = conflict (reported: mostly short abbreviations whose rare MONDO reading the gold query does not mean)
    ev = eval_concepts()
    leak, conflict, examples = {}, {}, []
    for it in items:
        g = ev.get(norm(it[0]))
        if g is None: continue
        for o in outputs_of(it):
            if it[1] is not None and it[1] in g: leak[o] = leak.get(o, 0) + 1
            else: conflict[o] = conflict.get(o, 0) + 1
        if it[1] is not None and it[1] not in g and len(examples) < 30: examples.append([it[0], it[1]])
    rep["eval_text_leak"] = leak; rep["eval_text_conflict"] = conflict; rep["eval_text_conflict_examples"] = examples
    for o in ("organ", "align", "sym"):
        if leak.get(o): bad.append(f"{leak[o]} training texts of the {o} output are evaluation queries with their gold concept")
    # one text, two validity labels
    seen = {}
    for it in items: seen.setdefault(it[0], set()).add(it[3])
    rep["valid_conflicts"] = sum(len(v) > 1 for v in seen.values())
    return rep, bad


def write_card(tag, card):
    os.makedirs(CARDS, exist_ok=True); p = CARDS + f"{tag}.json"
    old = json.load(open(p)) if os.path.exists(p) else {}
    json.dump(dict(old, **card), open(p, "w"), indent=1, ensure_ascii=False)


def add_bench(tag, name, res):
    """benchmark scores of a run's model, from ml/bench_judge.py."""
    p = CARDS + f"{tag}.json"
    if not os.path.exists(p): return
    c = json.load(open(p)); c.setdefault("bench", {})[name] = res; json.dump(c, open(p, "w"), indent=1, ensure_ascii=False)


def _diff(a, b):
    """what changed from card a to card b: data groups, arguments."""
    ch = []
    for g in sorted(set(a.get("data", {})) | set(b.get("data", {}))):
        x, y = a.get("data", {}).get(g, {}), b.get("data", {}).get(g, {})
        if x.get("sha") != y.get("sha"):
            if "files" not in y: ch.append(f"{g} 바뀜"); continue
            nf = sum(x.get("files", {}).get(f, [None, None])[1] != v[1] for f, v in y["files"].items())
            ch.append(f"{g} {x.get('rows', 0):,} → {y['rows']:,}행" if x.get("rows") != y["rows"] else f"{g} 행 수 같음, 내용 바뀐 파일 {nf}개")
    for k in sorted(set(a.get("args", {})) | set(b.get("args", {}))):
        if k in ("tag", "note", "stage"): continue
        if a.get("args", {}).get(k) != b.get("args", {}).get(k): ch.append(f"{k} {a.get('args', {}).get(k)} → {b.get('args', {}).get(k)}")
    return ch


def render():
    cards = [json.load(open(f)) for f in glob.glob(CARDS + "*.json")]
    cards.sort(key=lambda c: (c.get("started", ""), c.get("tag", "")))
    L = ["# Gemma judge 학습 기록", "",
         "`ml/tuning_ledger.py`가 `ml/results/tuning/*.json`에서 만든다. 손으로 고치지 않는다.",
         "각 실행의 데이터 파일(행 수, sha256), 설정, 결과는 카드에 있다. 아래는 단계별 요약이다.", ""]
    stages = []
    for c in cards:
        if c.get("stage") not in stages: stages.append(c.get("stage"))
    for s in stages:
        L += [f"## {s}", ""]
        prev = None
        for c in [c for c in cards if c.get("stage") == s]:
            g = c.get("git", {}); r = c.get("results", {})
            L.append(f"### {c['tag']} — {c.get('note', '')}")
            L.append("")
            L.append(f"- 시작 {c.get('started', '?')}, 커밋 `{g.get('commit', '?')}`" + (f" (커밋 안 된 변경 {g['n_dirty']}개)" if g.get("n_dirty") else "") + f", seed {c.get('args', {}).get('seed', '?')}")
            d = c.get("data", {})
            if d: L.append("- 데이터: " + ", ".join(f"{k} {v['rows']:,}" for k, v in d.items() if isinstance(v, dict) and v.get("rows")))
            if c.get("items"):
                it = c["items"]; L.append("- 학습 항목: " + ", ".join(f"{k} {v:,}" for k, v in it.items() if isinstance(v, int)))
                if it.get("by_source"): L.append("- 출처별 학습 항목: " + ", ".join(f"{k} {v:,}" for k, v in sorted(it["by_source"].items(), key=lambda x: -x[1])))
                if it.get("sources_left_out"): L.append("- 뺀 출처: " + ", ".join(it["sources_left_out"]))
            base = c.get("compare_to")
            ref = next((x for x in cards if x["tag"] == base), None) if base else prev
            if ref is not None:
                ch = _diff(ref, c); L.append(f"- {ref['tag']} 대비 바뀐 것: " + ("; ".join(ch) if ch else "없음(seed만)"))
            if c.get("checks"): L.append(f"- 학습 전 검사: {json.dumps(c['checks'], ensure_ascii=False)}")
            if r: L.append(f"- 내부 dev: " + ", ".join(f"{k} {v}" for k, v in r.items()))
            for name, b in (c.get("bench") or {}).items():
                L.append(f"- 벤치마크 {name}: " + ", ".join(f"{k} {v}" for k, v in b.items()))
            L.append(""); prev = c
    os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(LOG, len(cards), "cards")


if __name__ == "__main__":
    if "--manifest" in sys.argv: print(json.dumps(manifest(cache=P.CACHE), indent=1))
    else: render()
