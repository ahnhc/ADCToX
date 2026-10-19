"""Merge the Opus review verdicts (data/curated/review_opus/out/*.jsonl) into the datasets, gated by each batch's controls.

    ADC_RESEARCH_MODE=1 python ml/dataset_review_merge.py            # report only
    ADC_RESEARCH_MODE=1 python ml/dataset_review_merge.py --apply    # write the datasets, CSV exports and the report

Gate: a batch's changes are applied only when its hidden controls score at least CONTROL_MIN (organ: gold labels kept and
planted wrong labels changed back; others: planted errors caught). Changes from a failed batch go to review_queue.csv instead.
Control items themselves are never written to a dataset.

Applied where:
    organ      labels/verified_v4.jsonl (reviewer opus-5.5): changed concepts; linking_models.load_organ_labels reads it last
    sym/ko     judge2/gen/*.jsonl rebuilt from the pre-review files by ml/dataset_review_gen.py (the review numbers lines of
    junk       those files; rewriting in place applied the changes twice on shifted lines when the merge ran twice)
    profiles   disease_profiles/profiles_*.jsonl rewritten with the fixed fields
    mondo_ko   korean/review/rv_opus.jsonl (the merge of ml/mondo_ko_batches.py reads review files last)
CSV exports for people: data/curated/review_opus/csv/*.csv, one row per item with its source and review status.
"""
import csv, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated") + "/"
R = D + "review_opus/"
CONTROL_MIN = 0.75
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]


def read_out(name):
    rows = []
    try:
        for line in open(R + f"out/{name}.jsonl", encoding="utf-8"):
            line = line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except ValueError: pass
    except FileNotFoundError: return None
    return rows


def score(set_, man, rows):
    """-> (fraction of controls answered as expected, n controls seen)"""
    ctl = man["controls"]; hit = n = 0
    key = "id" if set_ in ("organ", "profiles", "mondo_ko") else "i"
    by = {str(r.get(key)): r for r in rows}
    for cid, exp in ctl.items():
        r = by.get(str(cid))
        if r is None: n += 1; continue
        n += 1; v = r.get("verdict")
        if set_ == "organ":                                            # the gold calibration labels are minimal (SLE: immune only); a
            got = set(r.get("organs", [])); gold = set(exp["organs"])     # change that keeps every gold organ and adds others still counts
            hit += (v == "keep" or (v == "change" and got >= gold)) if exp["expect"] == "keep" else (v == "change" and got >= gold)
        elif set_ == "junk": hit += v == "real"
        elif set_ in ("sym", "ko"): hit += v == "drop"
        elif set_ == "profiles": hit += v == "fix" and "ko" in (r.get("fields") or {})
        elif set_ == "mondo_ko": hit += v in ("fix", "unsure")
    return (hit / n if n else 0.0), n


def main(apply):
    man = json.load(open(R + "manifest.json")); rep = {}; queue = []; changes = {s: [] for s in ("organ", "sym", "ko", "junk", "profiles", "mondo_ko")}
    missing = []
    for name, m in sorted(man.items()):
        set_ = name.rsplit("_", 1)[0]; rows = read_out(name)
        if rows is None: missing.append(name); continue
        ctl_ids = set(m["controls"]); s, n = score(set_, m, rows); ok = s >= CONTROL_MIN
        key = "id" if set_ in ("organ", "profiles", "mondo_ko") else "i"
        real = [r for r in rows if str(r.get(key)) not in ctl_ids and not (key == "i" and isinstance(r.get("i"), int) and r["i"] < 0)]
        kinds = {}
        for r in real: kinds[r.get("verdict")] = kinds.get(r.get("verdict"), 0) + 1
        rep[name] = dict(items=len(real), lines=len(rows), controls=round(s, 3), n_controls=n, passed=ok, verdicts=kinds)
        for r in real:
            v = r.get("verdict")
            if v in ("keep", "junk") or v is None: continue
            (changes[set_] if ok else queue).append(dict(r, set=set_, batch=name))
    sets = {}
    for name, r in rep.items():
        s = name.rsplit("_", 1)[0]; a = sets.setdefault(s, dict(batches=0, passed=0, items=0, verdicts={}, control_mean=0.0))
        a["batches"] += 1; a["passed"] += r["passed"]; a["items"] += r["items"]; a["control_mean"] += r["controls"]
        for k, v in r["verdicts"].items(): a["verdicts"][k] = a["verdicts"].get(k, 0) + v
    for a in sets.values(): a["control_mean"] = round(a["control_mean"] / max(1, a["batches"]), 3)
    summary = dict(sets=sets, queued_from_failed_batches=len(queue), missing_outputs=missing, applied=apply)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if not apply: return
    os.makedirs(R + "csv", exist_ok=True)
    apply_organ(changes["organ"])
    import dataset_review_gen; dataset_review_gen.main(True)                     # sym / ko / junk: rebuilt from the pre-review files
    apply_profiles(changes["profiles"]); apply_mondo_ko(changes["mondo_ko"])
    with open(R + "review_queue.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["set", "batch", "id_or_i", "verdict", "value", "reason"])
        for q in queue: w.writerow([q["set"], q["batch"], q.get("id", q.get("i")), q.get("verdict"), json.dumps(q.get("organs") or q.get("text") or q.get("fields") or q.get("ko") or "", ensure_ascii=False), q.get("reason", "")])
    export_csv()
    json.dump(dict(summary, per_batch=rep), open(R + "report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def apply_organ(ch):
    rows = []
    for r in ch:
        if r["verdict"] == "change" and set(r.get("organs", [])) <= set(AXES) and len(r["organs"]) <= 4:
            rows.append(dict(id=r["id"], organs=sorted(set(r["organs"]), key=AXES.index), scope="axis" if r["organs"] else "no_axis", confidence=r.get("confidence", "medium"), reviewer="opus-5.5", note=r.get("reason", "")[:160]))
        elif r["verdict"] == "unclear":
            rows.append(dict(id=r["id"], organs=[], scope="unclear", confidence="low", reviewer="opus-5.5", note=r.get("reason", "")[:160]))
    with open(D + "concept_organs/labels/verified_v4.jsonl", "w", encoding="utf-8") as fh:
        for x in rows: fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("organ: verified_v4", len(rows))


def rewrite(pattern, decide):
    """rewrite each file of a glob: decide(index, row) -> row, or None to drop; -> (kept, dropped, fixed)"""
    files = sorted(glob.glob(pattern)); i = 0; kept = dropped = fixed = 0
    for f in files:
        out = []
        for line in open(f, encoding="utf-8"):
            if not line.strip(): continue
            x = json.loads(line); y = decide(i, x); i += 1
            if y is None: dropped += 1; continue
            if y is not x: fixed += 1
            out.append(y); kept += 1
        with open(f, "w", encoding="utf-8") as fh:
            for x in out: fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    return kept, dropped, fixed


def apply_profiles(ch):
    fix = {r["id"]: r.get("fields") or {} for r in ch if r.get("verdict") == "fix"}
    allowed = {"name", "en", "abbr", "ko", "ko_lay", "symptoms_en", "symptoms_ko", "everyday"}
    def decide(i, x):
        f = fix.get(x["id"])
        if not f: return x
        y = dict(x)
        for k, v in f.items():
            if k in allowed and (isinstance(v, list) or k in ("name", "everyday")): y[k] = v
        return y
    print("profiles", rewrite(D + "disease_profiles/profiles_*.jsonl", decide))


def apply_mondo_ko(ch):
    import re
    rows = [dict(id=r["id"], ko=r["ko"].strip(), alt=[], conf="high", reviewer="opus-5.5") for r in ch if r.get("verdict") == "fix" and re.search("[가-힣]", r.get("ko", ""))]
    with open(D + "korean/review/rv_opus.jsonl", "w", encoding="utf-8") as fh:
        for x in rows: fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("mondo_ko: rv_opus", len(rows), "(run ml/mondo_ko_batches.py --merge to rebuild mondo_ko.jsonl)")


def export_csv():
    """human-readable copies of the datasets after review."""
    import linking_models as LM
    from build_linking_pools import read_obo
    T = read_obo(); labels, _ = LM.load_organ_labels(); held = LM.gold_held(T)
    v4 = {x["id"]: x for x in map(json.loads, open(D + "concept_organs/labels/verified_v4.jsonl", encoding="utf-8"))} if os.path.exists(D + "concept_organs/labels/verified_v4.jsonl") else {}
    with open(R + "csv/organ_labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["mondo_id", "name", "organs", "in_training", "opus_review", "note"])
        for t in sorted(labels):
            if t not in T: continue
            r = v4.get(t); w.writerow([t, T[t]["name"], ";".join(sorted(labels[t], key=AXES.index)), "no (gold-related)" if t in held else "yes", (r["scope"] if r and r["scope"] == "unclear" else "changed") if r else "kept", (r or {}).get("note", "")])
    def dump(name, pattern, cols):
        with open(R + f"csv/{name}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(cols)
            for f in sorted(glob.glob(pattern)):
                for line in open(f, encoding="utf-8"):
                    if line.strip(): x = json.loads(line); w.writerow([";".join(x[c]) if isinstance(x.get(c), list) else x.get(c, "") for c in cols])
    dump("symptom_sentences", D + "judge2/gen/sym_*.jsonl", ["id", "lang", "style", "text"])
    dump("korean_expressions", D + "judge2/gen/ko_*.jsonl", ["id", "kind", "text"])
    dump("invalid_inputs", D + "judge2/gen/junk_*.jsonl", ["kind", "text"])
    dump("disease_profiles", D + "disease_profiles/profiles_*.jsonl", ["id", "name", "en", "abbr", "ko", "ko_lay", "symptoms_en", "symptoms_ko"])
    dump("korean_mondo_names", D + "korean/mondo_ko.jsonl", ["id", "en", "ko", "alt", "conf"])
    print("csv:", sorted(os.listdir(R + "csv")))


if __name__ == "__main__":
    main("--apply" in sys.argv)
