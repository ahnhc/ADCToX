"""Merge the two independent annotations of the disease-linking pilot, measure agreement, and build the gold file.

    python -I ml/merge_linking_gold.py prepare     -> annot/agreement_v0.json, annot/adjudicate.txt (disagreements only)
    python -I ml/merge_linking_gold.py finalize    -> gold_v0.jsonl (needs annot/adjudicated.jsonl for every disagreement)

A record is agreed when both annotators give the same validity, compatible concepts (each one's best is among the other's
acceptable concepts, or both null) and the same organ set; its gold concepts are the intersection of the two acceptable
lists (plus both bests). Anything else goes to the adjudicator, who sees both labels and the candidate pool.
"""
import json, re, sys, glob
from collections import Counter
D = "/home/hyeongchanahn/CONI/adctox/data/curated/disease_linking/"


def load():
    A, B = {}, {}
    for f in glob.glob(D + "annot/shard_*_A.jsonl"): A.update({x["qid"]: x for x in map(json.loads, open(f))})
    for f in glob.glob(D + "annot/shard_*_B.jsonl"): B.update({x["qid"]: x for x in map(json.loads, open(f))})
    return A, B


def kappa(a, b):
    labs = sorted(set(a) | set(b)); n = len(a); po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b); pe = sum(ca[l] * cb[l] for l in labs) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def compatible(x, y):
    if x["best"] is None and y["best"] is None: return True
    if x["best"] is None or y["best"] is None: return False
    return x["best"] in set(y["concepts"]) | {y["best"]} and y["best"] in set(x["concepts"]) | {x["best"]}


def prepare():
    A, B = load(); qids = sorted(A); assert set(A) == set(B) and len(A) == 600, (len(A), len(B))
    va, vb = [A[q]["validity"] for q in qids], [B[q]["validity"] for q in qids]
    both_valid = [q for q in qids if A[q]["validity"] == B[q]["validity"] == "valid"]
    jac = lambda q: (len(set(A[q]["organs"]) & set(B[q]["organs"])) / len(set(A[q]["organs"]) | set(B[q]["organs"]))) if (A[q]["organs"] or B[q]["organs"]) else 1.0
    dis = [q for q in qids if not (A[q]["validity"] == B[q]["validity"] and compatible(A[q], B[q]) and set(A[q]["organs"]) == set(B[q]["organs"]))]
    agr = dict(n=len(qids), validity_kappa=kappa(va, vb), validity_agree=sum(x == y for x, y in zip(va, vb)) / len(qids),
               concept_compatible_both_valid=sum(compatible(A[q], B[q]) for q in both_valid) / len(both_valid),
               organ_exact_both_valid=sum(set(A[q]["organs"]) == set(B[q]["organs"]) for q in both_valid) / len(both_valid),
               organ_jaccard_both_valid=sum(jac(q) for q in both_valid) / len(both_valid), n_disagreements=len(dis),
               validity_A=Counter(va), validity_B=Counter(vb))
    json.dump(agr, open(D + "annot/agreement_v0.json", "w"), indent=1); print(json.dumps(agr, indent=1))
    blocks = {}
    for f in glob.glob(D + "annot/shard_?.txt"):
        for b in open(f).read().split("### ")[1:]: blocks[b.split("\n", 1)[0].strip()] = "### " + b.strip()
    with open(D + "annot/adjudicate.txt", "w") as fh:
        for q in dis:
            strip = lambda x: {k: x[k] for k in ("validity", "concepts", "best", "pool_miss", "organs", "note")}
            fh.write(blocks[q] + f"\nannotator_1: {json.dumps(strip(A[q]))}\nannotator_2: {json.dumps(strip(B[q]))}\n\n")
    print("disagreements written:", len(dis))


def finalize():
    A, B = load(); adj = {x["qid"]: x for x in map(json.loads, open(D + "annot/adjudicated.jsonl"))}; out = []
    for q in sorted(A):
        a, b = A[q], B[q]
        if q in adj:
            x = adj[q]; rec = dict(qid=q, validity=x["validity"], concepts=sorted(set(x["concepts"]) | ({x["best"]} if x["best"] else set())), best=x["best"],
                                   pool_miss=x.get("pool_miss", False), organs=sorted(x["organs"]), source="adjudicated", note=x.get("note", ""))
        else:
            assert a["validity"] == b["validity"] and compatible(a, b) and set(a["organs"]) == set(b["organs"]), q
            c = (set(a["concepts"]) & set(b["concepts"])) | {v for v in (a["best"], b["best"]) if v}
            rec = dict(qid=q, validity=a["validity"], concepts=sorted(c), best=a["best"], pool_miss=a["pool_miss"] and b["pool_miss"], organs=sorted(a["organs"]), source="agreed", note="")
        rec["annotations"] = dict(A={k: a[k] for k in ("validity", "concepts", "best", "organs", "confidence")}, B={k: b[k] for k in ("validity", "concepts", "best", "organs", "confidence")})
        out.append(rec)
    with open(D + "gold_v0.jsonl", "w") as fh:
        for r in out: fh.write(json.dumps(r) + "\n")
    print("gold records", len(out), Counter(r["validity"] for r in out), Counter(r["source"] for r in out))


if __name__ == "__main__":
    {"prepare": prepare, "finalize": finalize}[sys.argv[1]]()
