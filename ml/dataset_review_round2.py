"""Round 2 of the Opus dataset review: verify round 1's changes blind, review the Korean MONDO names round 1 did not reach,
and relabel a blind sample of organ labels to measure the label error rate.

    ADC_RESEARCH_MODE=1 python ml/dataset_review_round2.py            # -> data/curated/review_opus/batches/{verify,mondo_ko2,blind}_*.json

    verify     every round-1 change that alters a training target or a shown name, as an A/B pair in random order:
               organ changes, ko drops and fixes, sym drops, profile fixes, Korean name fixes. 5 controls per batch: B is a
               corruption of A (random organs, another concept's text or name), so A must win.
    mondo_ko2  the 18,785 Korean MONDO names not in round 1 (all high and the rest of medium), 300 per batch, 6 swapped controls.
    blind      2,000 training concepts relabelled without seeing the current label (stratified by label size), 200 per batch,
               8 gold controls. Agreement with the current labels is the error estimate; disagreements go to adjudication.
Round-1 batch files must still be present (they hold the pre-review values that round 2 compares against).
"""
import glob, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
from dataset_review_batches import D, R, AXES, jl, chunks, write

SEED = 2027


def main():
    import linking_models as LM
    from build_linking_pools import read_obo
    from sample_label_concepts import line
    rng = random.Random(SEED); T = read_obo(); held = LM.gold_held(T); labels, _ = LM.load_organ_labels()
    man = json.load(open(R + "manifest.json")); man2 = {}
    out = {n: [json.loads(l) for l in open(R + f"out/{n}.jsonl", encoding="utf-8") if l.strip()] for n in man}

    # ---- A/B pairs from round 1's changes
    pairs = []
    def ctx_organ(b, t): return b[t]["concept"]
    for n in man:
        set_ = n.rsplit("_", 1)[0]; ctl = set(man[n]["controls"]); b = json.load(open(R + f"batches/{n}.json", encoding="utf-8"))
        if set_ == "organ":
            cur = {x["id"]: x for x in b}
            for r in out[n]:
                if r["id"] in ctl or r.get("verdict") != "change": continue
                pairs.append(dict(set="organ", key=r["id"], context=cur[r["id"]]["concept"], old=cur[r["id"]]["current"], new=sorted(r.get("organs", []))))
        elif set_ == "ko":
            cur = {x["i"]: x for x in b}
            for r in out[n]:
                i = r.get("i")
                if not isinstance(i, int) or i < 0 or str(i) in ctl or r.get("verdict") not in ("drop", "fix"): continue
                pairs.append(dict(set="ko", key=i, context=cur[i]["concept"] + f" | kind: {cur[i]['kind']}", old=cur[i]["text"], new=(r.get("text") or "").strip() if r["verdict"] == "fix" else "(drop: not an expression of this concept)"))
        elif set_ == "sym":
            cur = {s["i"]: (p, s) for p in b for s in p["sentences"]}
            for r in out[n]:
                i = r.get("i")
                if not isinstance(i, int) or i < 0 or r.get("verdict") != "drop": continue
                p, s = cur[i]
                pairs.append(dict(set="sym", key=i, context=f"disease: {p['name']} ({', '.join(p.get('ko', [])[:2])}); symptoms: {', '.join(p.get('symptoms_en', [])[:6])}", old=s["text"], new="(drop: does not describe this disease)"))
        elif set_ == "profiles":
            cur = {x["id"]: x for x in b}
            for r in out[n]:
                if r["id"] in ctl or r.get("verdict") != "fix" or not r.get("fields"): continue
                old = {k: cur[r["id"]].get(k) for k in r["fields"]}
                pairs.append(dict(set="profiles", key=r["id"], context=cur[r["id"]].get("concept") or cur[r["id"]]["name"], old=old, new=r["fields"]))
        elif set_ == "mondo_ko":
            cur = {x["id"]: x for x in b}
            for r in out[n]:
                if r["id"] in ctl or r.get("verdict") != "fix" or not r.get("ko"): continue
                pairs.append(dict(set="mondo_ko", key=r["id"], context=cur[r["id"]]["concept"], old=cur[r["id"]]["ko"], new=r["ko"].strip()))
    rng.shuffle(pairs)
    pool_text = [p["old"] for p in pairs if p["set"] in ("ko", "mondo_ko") and isinstance(p["old"], str)]
    for k, part in enumerate(chunks(pairs, 150)):
        items, controls = [], {}
        for j in range(5):                                                       # B is a corruption of A: A must win
            src = rng.choice(part)
            if src["set"] == "organ": bad = sorted(rng.sample([a for a in AXES if a not in src["new"]], 2))
            elif src["set"] == "profiles": bad = {kk: (["잘못된 이름"] if isinstance(v, list) else v) for kk, v in src["new"].items()}
            else: bad = rng.choice(pool_text)
            part.append(dict(set=src["set"], key=f"ctl{j}", context=src["context"], old=src["new"], new=bad)); controls[f"ctl{j}"] = dict(expect="A")
        for p in part:
            flip = rng.random() < 0.5
            a, b = (p["new"], p["old"]) if flip else (p["old"], p["new"])
            items.append(dict(set=p["set"], key=str(p["key"]), context=p["context"], A=a, B=b))
            if str(p["key"]).startswith("ctl"): controls[p["key"]] = dict(expect="B" if flip else "A")      # the uncorrupted side
            else: man2.setdefault("_pairs", {})[f"verify_{k:02d}:{p['key']}"] = dict(new_is="A" if flip else "B")
        man2[f"verify_{k:02d}"] = write(f"verify_{k:02d}", items, controls)

    # ---- the Korean names round 1 did not reach
    mk = [json.loads(l) for l in open(D + "korean/mondo_ko.jsonl", encoding="utf-8")]; mkd = {x["id"]: x for x in mk}
    seen = {x["id"] for n in man if n.startswith("mondo_ko") for x in json.load(open(R + f"batches/{n}.json", encoding="utf-8"))}
    rest = [x["id"] for x in mk if x["id"] not in seen]; rng.shuffle(rest); med = [x["id"] for x in mk if x["conf"] != "low"]
    for k, part in enumerate(chunks(rest, 294)):
        items = [dict(id=t, concept=line(T, t) if t in T else t, ko=mkd[t]["ko"], alt=mkd[t]["alt"], conf=mkd[t]["conf"]) for t in part]; controls = {}
        ids = {x["id"] for x in items}
        for j in range(6):
            t = rng.choice(med); o = rng.choice(med)
            if t in ids or mkd[t]["ko"] == mkd[o]["ko"]: continue
            items.append(dict(id=t, concept=line(T, t) if t in T else t, ko=mkd[o]["ko"], alt=[], conf="medium")); controls[t] = dict(expect="fix", wrong=mkd[o]["ko"], right=mkd[t]["ko"])
        rng.shuffle(items); man2[f"mondo_ko2_{k:02d}"] = write(f"mondo_ko2_{k:02d}", items, controls)

    # ---- blind relabel sample
    cal = json.load(open(D + "concept_organs/manifest.json"))["calibration"]; cal_ids = sorted(cal); rng.shuffle(cal_ids)
    train = [t for t in labels if t in T and t not in held]
    by = {0: [], 1: [], 2: [], 3: []}
    for t in train: by[min(3, len(labels[t]))].append(t)
    sample = []
    for size, n in ((0, 400), (1, 800), (2, 500), (3, 300)): rng.shuffle(by[size]); sample += by[size][:n]
    rng.shuffle(sample)
    for k, part in enumerate(chunks(sample, 200)):
        ctl = [cal_ids[(k * 8 + j) % len(cal_ids)] for j in range(8)]
        items = [dict(id=t, concept=line(T, t)) for t in part + ctl]; rng.shuffle(items)
        man2[f"blind_{k:02d}"] = write(f"blind_{k:02d}", items, {t: dict(expect="organs", organs=sorted(cal[t])) for t in ctl})
    json.dump(man2, open(R + "manifest2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sets = {}
    for b in man2:
        if b.startswith("_"): continue
        sets[b.rsplit("_", 1)[0]] = sets.get(b.rsplit("_", 1)[0], 0) + 1
    print(json.dumps(dict(pairs=len(pairs), per_set=sets, batches=sum(sets.values())), ensure_ascii=False))


if __name__ == "__main__":
    main()
