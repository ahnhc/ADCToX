"""Second concept-organ round (Haiku 5.5): compare with the first round and settle disagreements by a third vote.

    python ml/organ_verify_merge.py tiebreak     # after labels/v2_*.jsonl: writes batches/v3_*.txt for the concepts that disagree
    python ml/organ_verify_merge.py merge        # after labels/v3_*.jsonl: writes labels/verified_v2.jsonl and verify_report.json

verify concepts: old label (first round, or the strict relabel when there is one) vs the v2 label. Same organ set -> confirmed.
fill concepts:   the two v2 labels. Same -> accepted.
A disagreement gets a third independent label (v3) and the majority set wins; no majority -> left out (unclear).
Calibration concepts (gold) score each batch; a batch below CAL_MIN exact agreement is not used.
linking_models.load_organ_labels reads verified_v2.jsonl after the first-round files and before expert_*.jsonl.
"""
import glob, json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_linking_pools import read_obo
from sample_label_concepts import line

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "concept_organs") + "/"
AXES = {"haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"}
CAL_MIN = 0.6; PER_BATCH = 155


def read(prefix):
    """-> ({concept: [label dict]}, {batch: calibration exact-agreement})"""
    M = json.load(open(R + "verify_manifest.json")); cal = M["calibration"]; out, score = {}, {}
    for f in sorted(glob.glob(R + f"labels/{prefix}_*.jsonl")):
        L = []
        for l in open(f, encoding="utf-8"):
            try: x = json.loads(l)
            except ValueError: continue
            if not isinstance(x.get("organs"), list) or set(x["organs"]) - AXES: continue
            L.append(x)
        c = [set(x["organs"]) == set(cal[x["id"]]) for x in L if x["id"] in cal]
        b = os.path.basename(f)[:-6]; score[b] = sum(c) / len(c) if c else None
        if score[b] is not None and score[b] < CAL_MIN: continue
        for x in L:
            if x["id"] not in cal: out.setdefault(x["id"], []).append(x)
    return out, score


def key(x): return "unclear" if x.get("scope") == "unclear" else ",".join(sorted(x["organs"]))


def old_key(M, t):
    o = M["old"][t]; strict = [x for x in o if x["file"].startswith("relabel")]; x = (strict or o)[-1]
    return "unclear" if x.get("scope") == "unclear" else ",".join(sorted(x["organs"]))


def tiebreak():
    M = json.load(open(R + "verify_manifest.json")); V, score = read("v2"); T = read_obo(); todo = []
    for t in M["verify"]:
        if t in V and key(V[t][0]) != old_key(M, t): todo.append(t)
    for t in M["fill"]:
        v = V.get(t, [])
        if len(v) < 2 or key(v[0]) != key(v[1]): todo.append(t)
    import random; rng = random.Random(56); rng.shuffle(todo); cal_ids = sorted(M["calibration"])
    n = -(-len(todo) // PER_BATCH)
    for k in range(n):
        b = todo[k::n] + cal_ids[k * 8 % len(cal_ids):k * 8 % len(cal_ids) + 8]; rng.shuffle(b)
        open(R + f"batches/v3_{k:02d}.txt", "w", encoding="utf-8").write("\n".join(line(T, t) for t in b) + "\n")
    print(json.dumps(dict(calibration=score, tiebreak=len(todo), batches=n), indent=1))


def merge():
    M = json.load(open(R + "verify_manifest.json")); V, s2 = read("v2"); W, s3 = read("v3"); out = []; stats = Counter()
    for t in M["verify"] + M["fill"]:
        votes = ([old_key(M, t)] if t in M["old"] else []) + [key(x) for x in V.get(t, [])] + [key(x) for x in W.get(t, [])]
        if not votes: stats["no_label"] += 1; continue
        top, n = Counter(votes).most_common(1)[0]
        kind = "verify" if t in M["old"] else "fill"
        if n >= 2 and top != "unclear":
            first = len(set(votes[:2])) == 1
            stats[f"{kind}_{'agreed' if first else 'majority'}"] += 1
            organs = top.split(",") if top else []
            out.append(dict(id=t, organs=organs, scope="axis" if organs else "no_axis", confidence="agreed" if first else "majority",
                            votes=len(votes), reviewer="haiku-4.5+haiku-5.5" if kind == "verify" else "haiku-5.5x2", note=kind))
        else: stats[f"{kind}_unsettled"] += 1
    with open(R + "labels/verified_v2.jsonl", "w", encoding="utf-8") as fh:
        for x in out: fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    changed = sum(1 for x in out if x["note"] == "verify" and ",".join(x["organs"]) != old_key(M, x["id"]))
    rep = dict(calibration_v2=s2, calibration_v3=s3, counts=dict(stats), written=len(out), verify_label_changed=changed)
    json.dump(rep, open(R + "verify_report.json", "w"), indent=1); print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    {"tiebreak": tiebreak, "merge": merge}[sys.argv[1]]()
