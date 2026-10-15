"""Batches for the second concept-organ round (Haiku 5.5): verify every existing machine label and fill the frequent concepts
that have none.

    python ml/organ_verify_batches.py            # writes data/curated/concept_organs/batches/v2_*.txt and verify_manifest.json

  verify  every concept with a Haiku 4.5 label (batch_*, relabel_*), labelled once more without seeing the old label
  fill    review_queue.csv rows with use=training and no label yet, labelled twice in different batches (agreement)
Gold concepts and their parents and children are left out (the gold stays an evaluation set). Every batch carries 8 calibration
concepts from the gold (scored against the gold organs, never used for training), as in the first round.
After labelling, ml/organ_verify_merge.py compares the passes and writes the tie-break batches for the disagreements.
"""
import csv, glob, json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_linking_pools import read_obo
from sample_label_concepts import line, held_out

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "concept_organs") + "/"
SEED, PER_BATCH, N_CAL = 55, 150, 8


def old_labels():
    """concept -> list of earlier label sets (first round and strict relabel), calibration concepts excluded."""
    cal = set(json.load(open(R + "manifest.json"))["calibration"]); out = {}
    for f in sorted(glob.glob(R + "labels/batch_*.jsonl")) + sorted(glob.glob(R + "labels/relabel_*.jsonl")):
        for x in map(json.loads, open(f)):
            if x["id"] not in cal: out.setdefault(x["id"], []).append(dict(organs=sorted(x["organs"]), scope=x.get("scope"), file=os.path.basename(f)))
    return out


def main():
    rng = random.Random(SEED); T = read_obo(); held, _ = held_out(T); man = json.load(open(R + "manifest.json")); cal = man["calibration"]
    old = old_labels()
    verify = sorted(t for t in old if t in T and t not in held)
    queue = list(csv.DictReader(open(R + "review_queue.csv", encoding="utf-8")))
    fill = sorted({r["id"] for r in queue if r["use"] == "training" and r["id"] not in old and r["id"] in T and r["id"] not in held})
    items = verify + fill + fill; rng.shuffle(items)
    n = -(-len(items) // PER_BATCH); batches = [[] for _ in range(n)]
    for t in items:                                               # the two copies of a fill concept land in different batches
        k = min((k for k in range(n) if t not in batches[k]), key=lambda k: len(batches[k])); batches[k].append(t)
    cal_ids = sorted(cal); rng.shuffle(cal_ids); out = {}
    for k, b in enumerate(batches):
        c = [cal_ids[(k * N_CAL + i) % len(cal_ids)] for i in range(N_CAL)]; b = b + c; rng.shuffle(b); out[f"v2_{k:02d}"] = b
        with open(R + f"batches/v2_{k:02d}.txt", "w", encoding="utf-8") as fh: fh.write("\n".join(line(T, t) for t in b) + "\n")
    json.dump(dict(verify=verify, fill=fill, old={t: old[t] for t in verify}, calibration=cal, batches=out),
              open(R + "verify_manifest.json", "w"), indent=0, ensure_ascii=False)
    print(f"verify {len(verify)}  fill {len(fill)} (x2)  batches {n} of ~{PER_BATCH}+{N_CAL}")


if __name__ == "__main__":
    main()
