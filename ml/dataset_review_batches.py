"""Review batches for every training dataset of the Gemma judge and the search, for Claude Opus review agents.

    ADC_RESEARCH_MODE=1 python ml/dataset_review_batches.py        # -> data/curated/review_opus/batches/*.json, manifest.json

Six sets, 200 batches in all. Every batch carries hidden control items whose right answer is known (a gold organ label, or a
planted error: a sentence moved to another disease, a Korean term under the wrong concept, a real complaint among the invalid
inputs, a profile with another profile's name, a MONDO name swapped with another concept's). The controls score each agent;
ml/dataset_review_merge.py applies a batch's changes only when its controls pass. Gold concepts and their parents and children
appear only as controls, never as items whose label is changed for training.

    organ     21,031 concept organ labels (the consolidated training labels), 200 per batch, 8 gold controls   106 batches
    sym        7,900 symptom sentences of the 790 disease profiles, 25 profiles per batch, 5 moved sentences      32
    ko         4,983 Korean expressions for 1,561 concepts, 250 per batch, 5 under a wrong concept                 20
    junk       2,498 invalid inputs, ~360 per batch, 6 real complaints planted                                      7
    profiles     790 disease profiles, 40 per batch, 3 with another profile's Korean name                          20
    mondo_ko   4,500 Korean MONDO names: all 537 low-confidence + 3,963 medium sampled, 300 per batch, 6 swapped   15
"""
import csv, glob, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated") + "/"
R = D + "review_opus/"
SEED = 2026
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]


def jl(pattern):
    return [json.loads(l) for f in sorted(glob.glob(pattern)) for l in open(f, encoding="utf-8") if l.strip()]


def chunks(xs, n):
    return [xs[i:i + n] for i in range(0, len(xs), n)]


def write(name, items, controls):
    json.dump(items, open(R + f"batches/{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return dict(n=len(items), controls=controls)


def main():
    import linking_models as LM
    from build_linking_pools import read_obo
    from sample_label_concepts import line
    rng = random.Random(SEED); os.makedirs(R + "batches", exist_ok=True); os.makedirs(R + "out", exist_ok=True)
    T = read_obo(); held = LM.gold_held(T); labels, _ = LM.load_organ_labels(); man = {}

    # ---- organ labels: every training concept with its current label; 8 gold controls, half shown wrong
    cal = json.load(open(D + "concept_organs/manifest.json"))["calibration"]           # gold concept -> organs
    ids = sorted(t for t in labels if t in T and t not in held); rng.shuffle(ids)
    cal_ids = sorted(cal); rng.shuffle(cal_ids)
    for k, part in enumerate(chunks(ids, 200)):
        ctl = [cal_ids[(k * 8 + j) % len(cal_ids)] for j in range(8)]; controls = {}
        items = [dict(id=t, concept=line(T, t), current=sorted(labels[t])) for t in part]
        for j, t in enumerate(ctl):
            shown = sorted(cal[t])
            if j % 2:                                                               # a wrong label: expect "change" back to gold
                wrong = [a for a in AXES if a not in cal[t]]; shown = sorted((set(cal[t]) - set(list(cal[t])[:1])) | {rng.choice(wrong)}) if cal[t] else [rng.choice(wrong)]
            items.append(dict(id=t, concept=line(T, t), current=shown)); controls[t] = dict(expect="keep" if not j % 2 else "change", organs=sorted(cal[t]))
        rng.shuffle(items); man[f"organ_{k:03d}"] = write(f"organ_{k:03d}", items, controls)

    # ---- symptom sentences, by profile; 5 sentences moved to another profile
    P = {p["id"]: p for p in jl(D + "disease_profiles/profiles_*.jsonl")}
    sym = jl(D + "judge2/gen/sym_*.jsonl"); by = {}
    for i, x in enumerate(sym): by.setdefault(x["id"], []).append((i, x))
    pids = sorted(by); rng.shuffle(pids)
    for k, part in enumerate(chunks(pids, 25)):
        items, controls = [], {}
        for pid in part:
            p = P.get(pid, {}); rows = [dict(i=i, text=x["text"], lang=x["lang"], style=x["style"]) for i, x in by[pid]]
            items.append(dict(id=pid, name=p.get("name", T.get(pid, {}).get("name", pid)), en=p.get("en", [])[:3], ko=p.get("ko", [])[:2],
                              symptoms_en=p.get("symptoms_en", [])[:7], symptoms_ko=p.get("symptoms_ko", [])[:7], sentences=rows))
        for j in range(5):                                                          # a sentence of another disease, under this one
            a, b = rng.sample(range(len(items)), 2); src = rng.choice(items[b]["sentences"])
            fake = dict(i=-(1000 * k + j + 1), text=src["text"], lang=src["lang"], style=src["style"]); items[a]["sentences"].append(fake)
            rng.shuffle(items[a]["sentences"]); controls[str(fake["i"])] = dict(expect="drop", from_id=items[b]["id"], under=items[a]["id"])
        man[f"sym_{k:02d}"] = write(f"sym_{k:02d}", items, controls)

    # ---- Korean expressions; 5 under a wrong concept
    ko = jl(D + "judge2/gen/ko_*.jsonl"); order = list(range(len(ko))); rng.shuffle(order)
    for k, part in enumerate(chunks(order, 250)):
        items = [dict(i=i, id=ko[i]["id"], concept=line(T, ko[i]["id"]) if ko[i]["id"] in T else ko[i]["id"], text=ko[i]["text"], kind=ko[i]["kind"]) for i in part]
        controls = {}
        for j in range(5):
            a, b = rng.sample(range(len(items)), 2)
            if items[a]["id"] == items[b]["id"]: continue
            fake = dict(i=-(1000 * k + j + 1), id=items[a]["id"], concept=items[a]["concept"], text=items[b]["text"], kind=items[b]["kind"]); items.append(fake)
            controls[str(fake["i"])] = dict(expect="drop", text_of=items[b]["id"])
        rng.shuffle(items); man[f"ko_{k:02d}"] = write(f"ko_{k:02d}", items, controls)

    # ---- invalid inputs; 6 real complaints planted (symptom sentences and Korean disease terms)
    junk = jl(D + "judge2/gen/junk_*.jsonl"); order = list(range(len(junk))); rng.shuffle(order)
    real_pool = [x["text"] for x in sym if x["lang"] == "ko"] + [x["text"] for x in ko]
    for k, part in enumerate(chunks(order, 357)):
        items = [dict(i=i, text=junk[i]["text"], kind=junk[i]["kind"]) for i in part]; controls = {}
        for j in range(6):
            fake = dict(i=-(1000 * k + j + 1), text=rng.choice(real_pool), kind="?"); items.append(fake); controls[str(fake["i"])] = dict(expect="real")
        rng.shuffle(items); man[f"junk_{k:02d}"] = write(f"junk_{k:02d}", items, controls)

    # ---- disease profiles; 3 with another profile's Korean name
    prof = list(P.values()); rng.shuffle(prof)
    for k, part in enumerate(chunks(prof, 40)):
        items = [dict(p, concept=line(T, p["id"]) if p["id"] in T else "") for p in part]; controls = {}
        for a in rng.sample(range(len(items)), 3):
            b = rng.choice([x for x in range(len(items)) if x != a]); other = prof[(k * 40 + b) % len(prof)]["ko"]
            if not other or not items[a]["ko"]: continue
            items[a] = dict(items[a], ko=[other[0]] + items[a]["ko"][1:]); controls[items[a]["id"]] = dict(expect="fix", field="ko", wrong=other[0], right=part[a]["ko"][0])
        man[f"profiles_{k:02d}"] = write(f"profiles_{k:02d}", items, controls)

    # ---- Korean MONDO names: all low + a medium sample; 6 swapped with another concept's name
    mk = [json.loads(l) for l in open(D + "korean/mondo_ko.jsonl", encoding="utf-8")]; mkd = {x["id"]: x for x in mk}
    low = [x["id"] for x in mk if x["conf"] == "low"]; med = [x["id"] for x in mk if x["conf"] == "medium"]; rng.shuffle(med)
    pick = low + med[: 4500 - len(low) - 15 * 6]; rng.shuffle(pick)
    for k, part in enumerate(chunks(pick, 300 - 6)):
        items = [dict(id=t, concept=line(T, t) if t in T else t, ko=mkd[t]["ko"], alt=mkd[t]["alt"], conf=mkd[t]["conf"]) for t in part]; controls = {}
        for j in range(6):
            t = rng.choice(med); o = rng.choice(med)
            if t in {x["id"] for x in items} or mkd[t]["ko"] == mkd[o]["ko"]: continue
            items.append(dict(id=t, concept=line(T, t) if t in T else t, ko=mkd[o]["ko"], alt=[], conf="medium")); controls[t] = dict(expect="fix", wrong=mkd[o]["ko"], right=mkd[t]["ko"])
        rng.shuffle(items); man[f"mondo_ko_{k:02d}"] = write(f"mondo_ko_{k:02d}", items, controls)

    json.dump(man, open(R + "manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sets = {}
    for b in man: sets[b.rsplit("_", 1)[0]] = sets.get(b.rsplit("_", 1)[0], 0) + 1
    print(json.dumps(dict(batches=len(man), per_set=sets, items=sum(v["n"] for v in man.values())), ensure_ascii=False))


if __name__ == "__main__":
    main()
