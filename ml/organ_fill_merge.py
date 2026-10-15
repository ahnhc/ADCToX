"""Third concept-organ round (Haiku 5.5, GUIDE.md 'v3 additions'): labels/v4_*.jsonl -> labels/verified_v3.jsonl.

    python ml/organ_fill_merge.py

One vote per concept. A batch whose calibration concepts (gold) agree exactly less than CAL_MIN is not used. 'unclear' is left
out. linking_models.load_organ_labels reads verified_v3 after verified_v2 (so a 'no organ' label re-judged under the v3 rules
replaces the older one) and before expert labels.
"""
import glob, json, os
from collections import Counter

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "concept_organs") + "/"
AXES = {"haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"}
CAL_MIN = 0.6


def main():
    M = json.load(open(R + "fill_manifest.json")); cal = json.load(open(R + "manifest.json"))["calibration"]; todo = set(M["todo"])
    out, score, stats = {}, {}, Counter()
    for f in sorted(glob.glob(R + "labels/v4_*.jsonl")):
        L = []
        for line in open(f, encoding="utf-8"):
            try: x = json.loads(line)
            except ValueError: stats["bad_json"] += 1; continue
            if isinstance(x.get("organs"), list) and not set(x["organs"]) - AXES: L.append(x)
            else: stats["bad_organs"] += 1
        c = [set(x["organs"]) == set(cal[x["id"]]) for x in L if x["id"] in cal]
        b = os.path.basename(f)[:-6]; score[b] = round(sum(c) / len(c), 3) if c else None
        if score[b] is not None and score[b] < CAL_MIN: stats["batches_dropped"] += 1; continue
        for x in L:
            if x["id"] in cal or x["id"] not in todo: continue
            if x.get("scope") == "unclear": stats["unclear"] += 1; continue
            out[x["id"]] = dict(id=x["id"], organs=sorted(x["organs"]), scope="axis" if x["organs"] else "no_axis",
                                confidence=x.get("confidence", ""), reviewer="haiku-5.5", note="v3 fill")
    with open(R + "labels/verified_v3.jsonl", "w", encoding="utf-8") as fh:
        for x in out.values(): fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    rep = dict(batches=len(score), calibration_mean=round(sum(v for v in score.values() if v is not None) / max(1, sum(v is not None for v in score.values())), 3),
               written=len(out), of_todo=len(todo), with_organ=sum(bool(x["organs"]) for x in out.values()), **stats)
    json.dump(dict(report=rep, calibration=score), open(R + "fill_report.json", "w"), indent=1); print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
