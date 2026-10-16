"""Korean names for every human MONDO concept of the index: batches for translation agents, and the merge.

    ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache copy> python ml/mondo_ko_batches.py            # -> data/curated/korean/batches/ko_NNN.json
    python ml/mondo_ko_batches.py --merge                                                    # labels/*.jsonl -> mondo_ko.jsonl + report
Low-confidence and missing names went through a second pass (review/rv_NN.json -> review/rv_NN.jsonl), which wins.

Each batch item: id, English name, up to 3 exact synonyms, one parent name and the start of the definition (context only).
Agents write data/curated/korean/labels/ko_NNN.jsonl: {"id", "ko", "alt": [...], "conf": "high|medium|low"}; the rules are in
data/curated/korean/TRANSLATE.md. The merge keeps one name per concept and reports agreement with the names the app already
had (HIRA KCD names whose English is the MONDO name, curated profile names); those existing names still win in the app.
"""
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "korean") + "/"
N = 200


def batches():
    os.environ.setdefault("ADC_RESEARCH_MODE", "1")
    import numpy as np, adc_paths as P, suggest as SG
    from build_linking_pools import read_obo
    T = read_obo(); nh = SG.nonhuman()
    z = np.load(P.CACHE + "mondo_index.npz", allow_pickle=True)
    ids = [t for t in dict.fromkeys(str(x) for x in z["ids"]) if t in T and t not in nh and not T[t]["name"].startswith("obsolete")]
    os.makedirs(R + "batches", exist_ok=True); os.makedirs(R + "labels", exist_ok=True)
    items = [dict(id=t, name=T[t]["name"], syn=[s for s in T[t]["syn"] if s.lower() != T[t]["name"].lower()][:3],
                  parent=next((T[p]["name"] for p in T[t].get("parents", []) if p in T), ""), defn=(T[t].get("defn") or "")[:160]) for t in ids]
    for i in range(0, len(items), N):
        json.dump(items[i:i + N], open(R + f"batches/ko_{i // N:03d}.json", "w"), ensure_ascii=False, indent=0)
    print(len(items), "concepts", (len(items) + N - 1) // N, "batches")


def existing():
    """names the app already shows: profile Korean names, then KCD names whose English is exactly the MONDO name."""
    os.environ.setdefault("ADC_RESEARCH_MODE", "1")
    import recommend as RC, suggest as SG
    SG._KO[:] = [{}]                                              # without the translations themselves
    I = SG.index(RC); I.load_mondo()
    return dict(I.ko)


def merge():
    norm = lambda s: re.sub(r"[\s·\-,()'\[\]]", "", s)
    out, bad = {}, 0
    for f in sorted(glob.glob(R + "labels/ko_*.jsonl")) + sorted(glob.glob(R + "review/rv_*.jsonl")):     # the review pass wins
        for line in open(f, encoding="utf-8"):
            try: x = json.loads(line)
            except ValueError: bad += 1; continue
            ko = str(x.get("ko", "")).strip()
            if not x.get("id") or not re.search("[가-힣]", ko) or len(ko) > 60: bad += 1; continue
            out[x["id"]] = dict(id=x["id"], ko=ko, alt=[a for a in x.get("alt", []) if isinstance(a, str) and re.search("[가-힣]", a)][:3], conf=x.get("conf", ""))
    en = {it["id"]: it["name"] for f in glob.glob(R + "batches/ko_*.json") for it in json.load(open(f))}
    for t, x in out.items(): x["en"] = en.get(t, "")                # the MONDO preferred name: the index's first row may be a synonym
    old = existing(); both = [t for t in old if t in out]
    same = [t for t in both if norm(old[t]) == norm(out[t]["ko"]) or any(norm(old[t]) == norm(a) for a in out[t]["alt"])]
    todo = sum(len(json.load(open(f))) for f in glob.glob(R + "batches/ko_*.json"))
    with open(R + "mondo_ko.jsonl", "w", encoding="utf-8") as fh:
        for x in out.values(): fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    rep = dict(concepts=todo, translated=len(out), rejected_lines=bad, with_existing_name=len(both), same_as_existing=len(same),
               agreement=round(len(same) / max(1, len(both)), 3), conf={c: sum(x["conf"] == c for x in out.values()) for c in ("high", "medium", "low")},
               differ_examples=[(t, old[t], out[t]["ko"]) for t in both if t not in same][:40])
    json.dump(rep, open(R + "mondo_ko_report.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "differ_examples"}, ensure_ascii=False))


if __name__ == "__main__":
    merge() if "--merge" in sys.argv else batches()
