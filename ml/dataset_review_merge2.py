"""Apply round 2 of the Opus review (ml/dataset_review_round2.py batches): revert round-1 changes the blind A/B check did not
confirm, apply the second part of the Korean-name review, and measure the organ labels against the blind relabel.

    ADC_RESEARCH_MODE=1 python ml/dataset_review_merge2.py            # report
    ADC_RESEARCH_MODE=1 python ml/dataset_review_merge2.py --apply    # revert, apply, write report2.json and adjudication batches

verify     a round-1 change stays when the verifier chose the new side or "same"; otherwise it is reverted:
           organ -> removed from verified_v4.jsonl; ko / sym -> ml/dataset_review_gen.py rebuilds the files without it; profiles -> the old fields; mondo_ko -> removed from review/rv_opus.jsonl (then re-merged).
mondo_ko2  fixes appended to review/rv_opus.jsonl when the batch's controls pass.
blind      agreement of the blind labels with the current labels (exact, superset, Jaccard) by label size; disagreements are
           written as A/B batches (adjudicate_NN.json: current vs blind) for a third pass.
"""
import csv, glob, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
from dataset_review_batches import D, R, AXES, chunks, write
from dataset_review_merge import read_out, score, CONTROL_MIN


def main(apply):
    man2 = json.load(open(R + "manifest2.json")); pairs = man2.pop("_pairs"); rep = {}
    # ---- verify
    keep, revert, same, ctl_hit = [], [], 0, [0, 0]; by_set = {}
    for n in sorted(k for k in man2 if k.startswith("verify")):
        rows = read_out(n) or []; ctl = man2[n]["controls"]; b = {x["key"]: x for x in json.load(open(R + f"batches/{n}.json", encoding="utf-8"))}
        for r in rows:
            k = str(r.get("key")); v = r.get("better")
            if k in ctl: ctl_hit[1] += 1; ctl_hit[0] += v == ctl[k]["expect"]; continue
            p = pairs.get(f"{n}:{k}")
            if not p or k not in b: continue
            s = by_set.setdefault(b[k]["set"], dict(kept=0, reverted=0, same=0))
            if v == "same": same += 1; s["same"] += 1; keep.append((b[k], p))
            elif v == p["new_is"]: s["kept"] += 1; keep.append((b[k], p))
            else: s["reverted"] += 1; revert.append((b[k], p))
    rep["verify"] = dict(pairs=len(keep) + len(revert), kept=len(keep) - same, same=same, reverted=len(revert), controls=round(ctl_hit[0] / max(1, ctl_hit[1]), 3), by_set=by_set)
    # ---- mondo_ko2
    fixes, kinds, passed, nb = [], {}, 0, 0
    for n in sorted(k for k in man2 if k.startswith("mondo_ko2")):
        rows = read_out(n)
        if rows is None: continue
        nb += 1; s, _ = score("mondo_ko", man2[n], rows); ok = s >= CONTROL_MIN; passed += ok; ctl = set(man2[n]["controls"])
        for r in rows:
            if r.get("id") in ctl: continue
            kinds[r.get("verdict")] = kinds.get(r.get("verdict"), 0) + 1
            if ok and r.get("verdict") == "fix" and r.get("ko", "").strip(): fixes.append(dict(id=r["id"], ko=r["ko"].strip(), alt=[], conf="high", reviewer="opus-5.5-r2"))
    rep["mondo_ko2"] = dict(batches=nb, passed=passed, verdicts=kinds, fixes=len(fixes))
    # ---- blind
    import linking_models as LM
    from build_linking_pools import read_obo
    from sample_label_concepts import line
    T = read_obo(); labels, _ = LM.load_organ_labels(); cal = json.load(open(D + "concept_organs/manifest.json"))["calibration"]
    agree = {}; dis = []; c_hit = c_n = 0; n_unclear = 0
    for n in sorted(k for k in man2 if k.startswith("blind")):
        rows = read_out(n) or []; ctl = man2[n]["controls"]
        for r in rows:
            t = r.get("id"); got = set(r.get("organs", []))
            if t in ctl: c_n += 1; c_hit += got >= set(ctl[t]["organs"]); continue
            if t not in labels: continue
            if r.get("scope") == "unclear": n_unclear += 1; continue
            cur = set(labels[t]); size = min(3, len(cur)); a = agree.setdefault(size, dict(n=0, exact=0, superset=0, jaccard=0.0))
            a["n"] += 1; a["exact"] += got == cur; a["superset"] += got >= cur; a["jaccard"] += (len(got & cur) / len(got | cur)) if (got | cur) else 1.0
            if got != cur: dis.append(dict(set="organ", key=t, context=line(T, t), old=sorted(cur), new=sorted(got)))
    for a in agree.values():
        a["exact"] = round(a["exact"] / a["n"], 3); a["superset"] = round(a["superset"] / a["n"], 3); a["jaccard"] = round(a["jaccard"] / a["n"], 3)
    tot = sum(a["n"] for a in agree.values())
    rep["blind"] = dict(n=tot, unclear=n_unclear, by_label_size=agree, disagreements=len(dis), controls_superset=round(c_hit / max(1, c_n), 3))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    if not apply: return
    # ---- reverts
    v4p = D + "concept_organs/labels/verified_v4.jsonl"; v4 = [json.loads(l) for l in open(v4p, encoding="utf-8")]
    drop_v4 = {b["key"] for b, _ in revert if b["set"] == "organ"}
    with open(v4p, "w", encoding="utf-8") as fh:
        for x in v4:
            if x["id"] not in drop_v4: fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    # ko / sym reverts: ml/dataset_review_gen.py rebuilds those files from the pre-review lines without the reverted changes
    import dataset_review_gen; dataset_review_gen.main(True)
    restored = {"ko": [], "sym": []}; unfix = [b for b, _ in revert if b["set"] in ("ko", "sym")]
    prof_rev = {b["key"]: (b["A"] if _["new_is"] == "B" else b["B"]) for b, _ in revert if b["set"] == "profiles"}
    if prof_rev:
        for f in sorted(glob.glob(D + "disease_profiles/profiles_*.jsonl")):
            out = []
            for l in open(f, encoding="utf-8"):
                if not l.strip(): continue
                x = json.loads(l)
                if x["id"] in prof_rev: x = dict(x, **{k: v for k, v in prof_rev[x["id"]].items() if v is not None})
                out.append(x)
            open(f, "w", encoding="utf-8").write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    rvp = D + "korean/review/rv_opus.jsonl"; rv = [json.loads(l) for l in open(rvp, encoding="utf-8")]
    drop_rv = {b["key"] for b, _ in revert if b["set"] == "mondo_ko"}
    rv = [x for x in rv if x["id"] not in drop_rv] + fixes
    open(rvp, "w", encoding="utf-8").write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rv))
    # ---- adjudication batches for the blind disagreements (A/B, current vs blind, order random)
    rng = random.Random(2028); man3 = {}
    for k, part in enumerate(chunks(dis, 150)):
        items, pairs3 = [], {}
        for p in part:
            flip = rng.random() < 0.5; a, b_ = (p["new"], p["old"]) if flip else (p["old"], p["new"])
            items.append(dict(set="organ", key=p["key"], context=p["context"], A=a, B=b_)); pairs3[p["key"]] = dict(blind_is="A" if flip else "B")
        man3[f"adjudicate_{k:02d}"] = dict(write(f"adjudicate_{k:02d}", items, {}), pairs=pairs3)
    json.dump(man3, open(R + "manifest3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rep["reverted"] = dict(organ=len(drop_v4), ko_restored=len(restored["ko"]), sym_restored=len(restored["sym"]), ko_unfixed=len(unfix), profiles=len(prof_rev), mondo_ko=len(drop_rv))
    rep["adjudication_batches"] = len(man3)
    json.dump(rep, open(R + "report2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(dict(reverted=rep["reverted"], adjudication_batches=len(man3)), ensure_ascii=False))


if __name__ == "__main__":
    main("--apply" in sys.argv)
