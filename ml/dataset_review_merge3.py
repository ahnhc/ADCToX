"""Round 3: apply the adjudicated organ labels (blind relabel vs current label; ml/dataset_review_merge2.py wrote the batches).

    ADC_RESEARCH_MODE=1 python ml/dataset_review_merge3.py --apply

Where the adjudicator chose the blind label, the concept gets that label in labels/verified_v4.jsonl (reviewer opus-5.5-r3);
"same" and the current side leave the label as it is. The result is report3.json.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
from dataset_review_batches import D, R, AXES
from dataset_review_merge import read_out


def main(apply):
    man3 = json.load(open(R + "manifest3.json")); won = {"blind": 0, "current": 0, "same": 0}; changes = []
    for n, m in sorted(man3.items()):
        rows = read_out(n) or []; b = {x["key"]: x for x in json.load(open(R + f"batches/{n}.json", encoding="utf-8"))}
        for r in rows:
            k = r.get("key"); p = m["pairs"].get(k)
            if not p or k not in b: continue
            v = r.get("better")
            if v == "same": won["same"] += 1
            elif v == p["blind_is"]:
                won["blind"] += 1; organs = b[k][v]
                if set(organs) <= set(AXES) and len(organs) <= 4: changes.append(dict(id=k, organs=sorted(organs, key=AXES.index), scope="axis" if organs else "no_axis", confidence="medium", reviewer="opus-5.5-r3", note="blind relabel adjudicated: " + r.get("reason", "")[:120]))
            else: won["current"] += 1
    rep = dict(adjudicated=sum(won.values()), won=won, applied=len(changes) if apply else 0)
    print(json.dumps(rep, ensure_ascii=False))
    if not apply: return
    p = D + "concept_organs/labels/verified_v4.jsonl"; rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    ids = {x["id"] for x in changes}; rows = [x for x in rows if x["id"] not in ids] + changes
    open(p, "w", encoding="utf-8").write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
    json.dump(rep, open(R + "report3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main("--apply" in sys.argv)
