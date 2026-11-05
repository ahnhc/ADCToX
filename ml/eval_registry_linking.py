"""How well free text reaches a registry condition (the rules keyed on a condition apply to a patient only through it).

    python -I ml/eval_registry_linking.py [--split holdout|tune|all] [--show]

Reads data/curated/registry_linking/queries.jsonl: typed inputs with the registry condition each should reach. Every input is
resolved as the app resolves it (ml/recommend.py): the alias table and registry labels first (_by_label), else the organ judge's
concept (scratch_runtime.judge, the installed model) mapped to a registry condition (_by_concept).

    right      the input reaches its condition
    wrong      it reaches another condition
    unlinked   it reaches none (the judge's concept stands for no registry condition, or the judge rejects the text)

Inputs with no condition ("ambiguous": MS, CAD, PE ...) have several clinical meanings, so the right result is no link: they
are reported apart: no alias may claim one, the judge may still link some.

The benchmark is written by an LLM ("author": "llm"); no clinician has read it. The split is by condition, sha1(id) % 2: the
alias table (conf/registry_aliases.yaml) was built looking at the tune half only. Run the holdout once, after the table is final.
"""
import argparse, collections, hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P

QUERIES = P.REPO + "data/curated/registry_linking/queries.jsonl"


def split_of(condition):
    return "tune" if int(hashlib.sha1(condition.encode()).hexdigest(), 16) % 2 == 0 else "holdout"


def load(path=QUERIES):
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    for r in rows:
        assert r.get("author") == "llm", r
        if r["condition"]: assert r["split"] == split_of(r["condition"]), r
    return rows


def resolve(texts, RC, SR):
    """-> [(registry id or None, how)] with how in alias, judge, none"""
    out, judged = [], [t for t in texts if t.lower() not in RC._by_label]
    J = dict(zip(judged, SR.judge(judged))) if judged else {}
    for t in texts:
        if t.lower() in RC._by_label: out.append((RC._by_label[t.lower()], "alias")); continue
        r = J[t]; cid = RC._by_concept.get(r["concept"]) if r["ok"] and r["concept"] else None
        out.append((cid, "judge" if cid else "none"))
    return out


def score(rows, got):
    cls = lambda r, g: "right" if g == r["condition"] else "unlinked" if g is None else "wrong"
    return [cls(r, g[0]) for r, g in zip(rows, got)]


def table(title, groups):
    print(f"\n{title}")
    for k, v in sorted(groups.items()):
        n = sum(v.values()); print(f"  {k:34s} n={n:3d}  right {v['right']:3d}  wrong {v['wrong']:3d}  unlinked {v['unlinked']:3d}  ({v['right'] / n:.0%})")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--split", default="holdout", choices=["holdout", "tune", "all"]); ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    import recommend as RC, scratch_runtime as SR
    assert SR.available(), "the organ judge is not installed"
    rows = [r for r in load() if r["condition"] and a.split in ("all", r["split"])]
    amb = [r for r in load() if not r["condition"]]
    got, got_amb = resolve([r["query"] for r in rows], RC, SR), resolve([r["query"] for r in amb], RC, SR)
    res = score(rows, got); n = len(rows); c = collections.Counter(res)
    print(f"split {a.split}: {n} inputs (LLM-written, not clinician-reviewed), {len({r['condition'] for r in rows})} conditions")
    print(f"right {c['right']} ({c['right'] / n:.1%})   wrong {c['wrong']} ({c['wrong'] / n:.1%})   unlinked {c['unlinked']} ({c['unlinked'] / n:.1%})")
    by_c, by_f = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for r, x in zip(rows, res): by_c[r["condition"]][x] += 1; by_f[r["form"]][x] += 1
    table("per condition", by_c); table("per form", by_f)
    kept = sum(g[0] is None for g in got_amb)
    print(f"\nambiguous short forms ({len(amb)}), no alias may claim one: unlinked {kept}, by alias {sum(g[1] == 'alias' for g in got_amb)}, by the judge {sum(g[1] == 'judge' for g in got_amb)}"
          + "".join(f"\n  {r['query']} -> {g[0]} ({g[1]})" for r, g in zip(amb, got_amb) if g[0]))
    if a.show:
        print("\nnot right:")
        for r, g, x in zip(rows, got, res):
            if x != "right": print(f"  {x:8s} {r['query']!r:48s} want {r['condition']:26s} got {g[0]} ({g[1]})")


if __name__ == "__main__":
    main()
