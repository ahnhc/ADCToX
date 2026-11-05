"""First refit experiment (ADCTOX_RELEASE_DEV_GOLD=1), scored on dev only, seed by seed, against the same seeds of the baseline.

    ADC_RESEARCH_MODE=1 python ml/score_refit.py --baseline <x2te7> <x2te8> <x2te9> --arm A <rfa7> <rfa8> <rfa9> --arm B <rfb7> <rfb8> <rfb9>

A run directory holds bench.json (ml/bench_judge.py) and known.json (ml/known_eval.py), both of the x2te composition (judge + evidence
reader, MONDO_FIRST=0.02), and its name ends in its seed.
Scores: gold_v0 macro-F1 on all valid dev and on abbrev+typo+lay, gate rejections of valid abbrev+typo+lay inputs, Boxed misses (a missed
organ of a question counts once per ADC with a Boxed warning on it, ml/data/label_evidence.json), known dev macro-F1 (English decides; Korean printed).
Predicate, declared before the first result: PASS if the seed mean gains at least +0.03 on abbrev+typo+lay gold_v0, rejections reach at most
7 of 137, and known dev falls by at most 0.01. FAIL if that gain is under +0.01. Otherwise INCONCLUSIVE.
Released dev concepts are no longer unseen, so gold dev here measures known concepts in new phrasing; the unseen 0.778 does not apply.
"""
import argparse, json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")

HARD = ("abbrev", "typo", "lay")
PASS_GAIN, FAIL_GAIN, MAX_REJECTIONS, MAX_KNOWN_DROP = 0.03, 0.01, 7, 0.01


def verdict(gain, rejections, known_drop):
    if gain < FAIL_GAIN: return "FAIL"
    return "PASS" if gain >= PASS_GAIN and rejections <= MAX_REJECTIONS and known_drop <= MAX_KNOWN_DROP else "INCONCLUSIVE"


def seed_of(run):
    m = re.search(r"(\d+)$", os.path.basename(run.rstrip("/\\")))
    if not m: raise SystemExit(f"{run}: a run directory's name ends in its seed")
    return int(m.group(1))


def paired(baseline, arm):
    b, a = {seed_of(r): r for r in baseline}, {seed_of(r): r for r in arm}
    if sorted(b) != sorted(a): raise SystemExit(f"seeds differ: baseline {sorted(b)}, arm {sorted(a)}")
    return [(s, b[s], a[s]) for s in sorted(b)]


def questions():
    """gold_v0 and known questions with their dev rows; nothing below indexes any other row."""
    if os.environ.setdefault("ADCTOX_LABELS", "v51") != "v51": raise SystemExit("known answers are the v51 organ table: ADCTOX_LABELS must be v51")
    import adc_paths as P, bench_judge as BJ, eval_linking as EL, known_eval as KE
    _, gold, groups, _, _ = BJ.questions(); dev = [i for i, g in enumerate(groups) if EL.split_of(g) == "dev"]
    known = {}
    for lg, qs in KE.questions().items():
        known[lg] = (len(qs), [dict(validity="valid", concepts=[q["id"]], best=q["id"], organs=q["organs"], category=q["kind"]) for q in qs], [i for i, q in enumerate(qs) if q["split"] == "dev"])
    evidence = json.load(open(P.REPO + "ml/data/label_evidence.json", encoding="utf-8"))["evidence"]
    boxed = {a: sum(((e.get("organs") or {}).get(a) or {}).get("level") == "boxed" for e in evidence.values()) for a in EL.AXES}
    return dict(EL=EL, gold=gold, n=len(groups), dev=dev, hard=[i for i in dev if gold[i]["category"] in HARD], known=known, boxed=boxed, sha=BJ.questions_sha())


def f1(q, rows, gold, ix):
    pred = {i: ((rows[i] or {}).get("concept"), (rows[i] or {}).get("organs", [])) for i in ix}
    return q["EL"].metrics(pred, gold, ix)["macro_f1"]


def score(run, q):
    bench = json.load(open(os.path.join(run, "bench.json"), encoding="utf-8")); known = json.load(open(os.path.join(run, "known.json"), encoding="utf-8"))
    if bench.get("questions") != q["sha"]: raise SystemExit(f"{run}: benchmark questions {bench.get('questions')}, these are {q['sha']}")
    if known.get("split") != "dev": raise SystemExit(f"{run}: known.json is split {known.get('split')}, dev only")
    rows, gold = bench["per"]["en"], q["gold"]
    if len(rows) != q["n"]: raise SystemExit(f"{run}: {len(rows)} rows for {q['n']} questions")
    hard_valid = [i for i in q["hard"] if gold[i]["validity"] == "valid"]
    out = dict(gold_v0=f1(q, rows, gold, q["dev"]), hard=f1(q, rows, gold, q["hard"]), rejected=sum("sim" not in rows[i] for i in hard_valid), hard_valid=len(hard_valid), boxed_missed=0, boxed_total=0)
    for i in q["dev"]:
        if gold[i]["validity"] != "valid": continue
        truth = set(gold[i]["organs"]); got = set((rows[i] or {}).get("organs", []))
        out["boxed_missed"] += sum(q["boxed"][a] for a in truth - got); out["boxed_total"] += sum(q["boxed"][a] for a in truth)
    for lg, (n, kg, kx) in q["known"].items():
        kr = known["per"][lg]
        if len(kr) != n: raise SystemExit(f"{run}: {len(kr)} known {lg} rows for {n} questions")
        out["known_" + lg] = f1(q, kr, kg, kx)
    return out


def line(name, s, ref=None):
    d = lambda k: f" ({s[k] - ref[k]:+.3f})" if ref else ""
    known = " ".join(f"known_{lg} {s['known_' + lg]:.3f}{d('known_' + lg)}" for lg in ("en", "ko") if "known_" + lg in s)
    return f"{name:8} gold_v0 {s['gold_v0']:.3f}{d('gold_v0')} abbrev+typo+lay {s['hard']:.3f}{d('hard')} rejected {s['rejected']}/{s['hard_valid']} boxed_missed {s['boxed_missed']}/{s['boxed_total']} {known}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", nargs="+", required=True); ap.add_argument("--arm", nargs="+", action="append", default=[], metavar="NAME RUN")
    ap.add_argument("--split", default="dev"); ap.add_argument("--test", action="store_true"); a = ap.parse_args(argv)
    if a.test or a.split != "dev" or any("final_test" in x for x in a.baseline + [r for arm in a.arm for r in arm]):
        raise SystemExit("score_refit reads dev only; it refuses the test split")
    pairs = [(arm[0], paired(a.baseline, arm[1:])) for arm in a.arm]
    q = questions(); base = {seed_of(r): score(r, q) for r in a.baseline}
    print("baseline")
    for s in sorted(base): print(line(f"seed {s}", base[s]))
    print(f"mean     gold_v0 {np.mean([b['gold_v0'] for b in base.values()]):.3f} abbrev+typo+lay {np.mean([b['hard'] for b in base.values()]):.3f} rejected {np.mean([b['rejected'] for b in base.values()]):.1f} "
          f"boxed_missed {np.mean([b['boxed_missed'] for b in base.values()]):.1f} known_en {np.mean([b['known_en'] for b in base.values()]):.3f}")
    for name, runs in pairs:
        got = {s: score(r, q) for s, _, r in runs}
        print(f"arm {name} (difference from the same baseline seed)")
        for s in sorted(got): print(line(f"seed {s}", got[s], base[s]))
        gain = float(np.mean([got[s]["hard"] - base[s]["hard"] for s in got])); rej = float(np.mean([got[s]["rejected"] for s in got]))
        drop = float(np.mean([base[s]["known_en"] - got[s]["known_en"] for s in got]))
        print(f"mean     abbrev+typo+lay gain {gain:+.3f}, rejected {rej:.1f}, known_en fall {drop:+.3f} -> {verdict(gain, rej, drop)}")


if __name__ == "__main__":
    main()
