"""Rebuild the judge's generated texts (judge2/gen/sym_*, ko_*, junk_*) from the pre-review files and the Opus review, in one pass.

    ADC_RESEARCH_MODE=1 python ml/dataset_review_gen.py            # report
    ADC_RESEARCH_MODE=1 python ml/dataset_review_gen.py --apply    # rewrite the files and the CSV exports

The review's `i` is a line number in the files before the review (commit BASE). ml/dataset_review_merge.py applied the
changes to the files in place, so running it twice applied them again on shifted lines: fixes landed on other sentences and
other lines were dropped. This script always starts from BASE, so it gives the same files however often it runs.

Applied: round-1 drops and fixes from batches whose controls passed (manifest.json, report.json), minus the round-2 changes
the blind A/B check did not confirm (manifest2.json, out/verify_*). Junk: the round-1 real complaints are removed and exact
duplicate texts are kept once. ko_restored.jsonl and sym_restored.jsonl are removed: the reverted drops stay in place.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
from dataset_review_merge import D, R, read_out

BASE = "61faa4d"
GEN = "data/curated/judge2/gen/"
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def base_files(prefix):
    """-> [(file name, [rows])] of judge2/gen/<prefix>_NN.jsonl at BASE, in name order (the order the review numbered)."""
    names = subprocess.run(["git", "ls-tree", "--name-only", BASE, GEN], capture_output=True, text=True, cwd=REPO, check=True).stdout.split()
    out = []
    for f in sorted(n for n in names if os.path.basename(n).startswith(prefix + "_") and n.endswith(".jsonl")):
        text = subprocess.run(["git", "show", f"{BASE}:{f}"], capture_output=True, text=True, cwd=REPO, check=True).stdout
        out.append((os.path.basename(f), [json.loads(l) for l in text.splitlines() if l.strip()]))
    return out


def round1(set_):
    """-> {i: verdict row} for the non-control items of passed round-1 batches that change something."""
    man = json.load(open(R + "manifest.json")); rep = json.load(open(R + "report.json"))["per_batch"]; ch = {}
    for n, m in man.items():
        if n.rsplit("_", 1)[0] != set_ or not rep[n]["passed"]: continue
        ctl = set(m["controls"])
        for r in read_out(n) or []:
            i = r.get("i")
            if isinstance(i, int) and i >= 0 and str(i) not in ctl and r.get("verdict") in ("fix", "drop", "real"): ch[i] = r
    return ch


def reverted():
    """-> {(set, i)} round-1 changes the round-2 A/B check reverted (the verifier chose the old side)."""
    man2 = json.load(open(R + "manifest2.json")); pairs = man2.pop("_pairs"); out = set()
    for n in sorted(k for k in man2 if k.startswith("verify")):
        b = {x["key"]: x for x in json.load(open(R + f"batches/{n}.json", encoding="utf-8"))}; ctl = man2[n]["controls"]
        for r in read_out(n) or []:
            k = str(r.get("key")); p = pairs.get(f"{n}:{k}")
            if k in ctl or not p or k not in b: continue
            if r.get("better") not in ("same", p["new_is"]) and b[k]["set"] in ("sym", "ko"): out.add((b[k]["set"], int(k)))
    return out


def build():
    rev = reverted(); res = {}; stats = {}
    for set_ in ("sym", "ko", "junk"):
        ch = {i: r for i, r in round1(set_).items() if (set_, i) not in rev}; i = 0; seen = set(); files = []; s = dict(base=0, dropped=0, fixed=0, duplicates=0)
        for name, rows in base_files(set_):
            out = []
            for x in rows:
                r = ch.get(i); i += 1; s["base"] += 1
                if r and r["verdict"] in ("drop", "real"): s["dropped"] += 1; continue
                if r and r["verdict"] == "fix" and (r.get("text") or "").strip(): x = dict(x, text=r["text"].strip()); s["fixed"] += 1
                if set_ == "junk":
                    t = str(x.get("text", "")).strip()
                    if t in seen: s["duplicates"] += 1; continue
                    seen.add(t)
                out.append(x)
            files.append((name, out))
        s["kept"] = sum(len(o) for _, o in files); s["reverted"] = sum(1 for k in rev if k[0] == set_); res[set_] = files; stats[set_] = s
    return res, stats


def main(apply):
    res, stats = build(); print(json.dumps(stats, indent=1))
    if not apply: return
    for set_, files in res.items():
        for name, rows in files:
            open(D + "judge2/gen/" + name, "w", encoding="utf-8").write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
        p = D + f"judge2/gen/{set_}_restored.jsonl"
        if os.path.exists(p): os.remove(p)
    from dataset_review_merge import export_csv
    export_csv()


if __name__ == "__main__":
    main("--apply" in sys.argv)
