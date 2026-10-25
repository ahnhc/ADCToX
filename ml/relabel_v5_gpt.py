"""Run one stage of the v5 organ labelling through the OpenAI API (see data/curated/concept_organs/v5/GPT_TASK.md).

    pip install openai ; export OPENAI_API_KEY=...
    python ml/relabel_v5_gpt.py --stage pass1 --model <model> [--effort high] [--workers 16] [--limit 20]
    python ml/relabel_v5_gpt.py --stage adjudicate --model <model> --effort high
    python ml/relabel_v5_gpt.py --stage audit --model <model> --effort high
    python ml/relabel_v5_gpt.py --stage pass1 --mock          # no API: fills outputs from the older labels, to test the plumbing

Every call starts fresh: the instructions (GUIDE_v5.md, plus ADJUDICATE.md or AUDIT.md) and one batch, nothing else, so passes
stay independent. Batches whose output exists and is valid are skipped, so the command can be re-run after a stop. An output that
fails the format checks is retried (up to --retries) with the problems listed; a batch that still fails is reported, not written.
Each call is logged to v5/runs.jsonl (stage, batch, model, effort, attempt, tokens, seconds, ok).
"""
import argparse, glob, json, os, random, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relabel_v5 as R

GUIDE = R.P.REPO + "data/curated/concept_organs/GUIDE_v5.md"
LOCK = threading.Lock()


def instructions(stage):
    g = open(GUIDE, encoding="utf-8").read()
    if stage == "adjudicate": g += "\n\n" + open(R.V5 + "ADJUDICATE.md", encoding="utf-8").read()
    if stage == "audit": g += "\n\n" + open(R.V5 + "AUDIT.md", encoding="utf-8").read()
    return g


def ask(stage, items):
    n = len(items)
    if stage.startswith("pass"):
        return f"Label these {n} concepts. Output exactly {n} JSON lines, one per concept, in the same order, and nothing else.\n\n" + json.dumps(items, ensure_ascii=False, indent=1)
    if stage == "adjudicate":
        return f"Adjudicate these {n} items. Output exactly {n} JSON lines, one per item, in the same order, and nothing else.\n\n" + json.dumps(items, ensure_ascii=False, indent=1)
    return f"Audit these {n} items. Output exactly {n} JSON lines, one per item, in the same order, and nothing else.\n\n" + json.dumps(items, ensure_ascii=False, indent=1)


def problems(stage, want, text):
    rows = [json.loads(l) for l in text.splitlines() if l.strip() and not l.strip().startswith("```")]
    bad = []
    if [r.get("id") for r in rows] != want: bad.append(f"expected {len(want)} lines with ids in this order: {want}")
    for r in rows:
        if stage == "audit":
            if r.get("verdict") not in ("ok", "corrected"): bad.append(f"{r.get('id')}: verdict must be ok or corrected")
            elif r["verdict"] == "corrected": bad += [f"{r.get('id')}: {b}" for b in R.valid_label(r.get("corrected", {}))]
        else: bad += [f"{r.get('id')}: {b}" for b in R.valid_label(r)]
    return bad


def mock(stage, items):
    v4 = json.load(open(R.V5 + "input/v4_labels.json")); rng = random.Random(stage + (items[0].get("record") or items[0])["id"]); out = []
    for it in items:
        t = (it.get("record") or it)["id"]; o = v4.get(t, []); p = o[:1]; i = [a for a in o[1:]]
        if stage.startswith("pass") and o and rng.random() < 0.3: i = i[:-1] if i else ["otologic"] if "otologic" not in p else []
        lab = dict(id=t, primary=p, involved=i, no_axis=not o, confidence="high", basis="mock")
        out.append(dict(id=t, verdict="ok", reason="mock") if stage == "audit" else dict(lab, decisions={}) if stage == "adjudicate" else lab)
    return "\n".join(json.dumps(x) for x in out)


def run_batch(a, client, f):
    out = R.V5 + f"{a.stage}/out/" + os.path.basename(f)[:-5] + ".jsonl"; os.makedirs(os.path.dirname(out), exist_ok=True)
    items = json.load(open(f, encoding="utf-8")); want = [(it.get("record") or it)["id"] for it in items]
    if os.path.exists(out) and not problems(a.stage, want, open(out, encoding="utf-8").read()): return "skip"
    msg = ask(a.stage, items); sysmsg = instructions(a.stage)
    for attempt in range(1, a.retries + 1):
        t0 = time.time(); usage = {}
        try:
            if a.mock: text = mock(a.stage, items)
            else:
                kw = dict(model=a.model, instructions=sysmsg, input=msg)
                if a.effort: kw["reasoning"] = {"effort": a.effort}
                r = client.responses.create(**kw); text = r.output_text
                u = getattr(r, "usage", None); usage = dict(input=getattr(u, "input_tokens", None), output=getattr(u, "output_tokens", None)) if u else {}
            bad = problems(a.stage, want, text)
        except Exception as e:
            text, bad = "", [f"error: {type(e).__name__}: {str(e)[:200]}"]; time.sleep(min(60, 5 * attempt))
        with LOCK:
            open(R.V5 + "runs.jsonl", "a").write(json.dumps(dict(stage=a.stage, batch=os.path.basename(f), model="mock" if a.mock else a.model, effort=a.effort,
                                                                 attempt=attempt, seconds=round(time.time() - t0, 1), ok=not bad, problems=bad[:3], **usage)) + "\n")
        if not bad:
            open(out, "w", encoding="utf-8").write(text.strip() + "\n"); return "ok"
        if text and not bad[0].startswith("error"):
            msg = ask(a.stage, items) + "\n\nYour previous answer had these problems; answer again in full:\n- " + "\n- ".join(bad[:10])
    return "failed"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", required=True); ap.add_argument("--model", default=None); ap.add_argument("--effort", default="high")
    ap.add_argument("--workers", type=int, default=16); ap.add_argument("--retries", type=int, default=3); ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--mock", action="store_true"); a = ap.parse_args()
    if not a.mock and not a.model: raise SystemExit("--model is required (the most capable reasoning model available)")
    client = None
    if not a.mock:
        from openai import OpenAI
        client = OpenAI()
    files = sorted(glob.glob(R.V5 + f"{a.stage}/in/*.json"))[: a.limit]; os.makedirs(R.V5 + f"{a.stage}/out", exist_ok=True)
    res = {}
    with ThreadPoolExecutor(a.workers) as ex:
        for f, s in zip(files, ex.map(lambda f: run_batch(a, client, f), files)): res[s] = res.get(s, 0) + 1
    print(json.dumps(dict(stage=a.stage, batches=len(files), **res)))


if __name__ == "__main__":
    main()
