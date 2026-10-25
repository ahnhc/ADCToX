"""Run one stage of the v5 organ labelling through `codex exec` on a ChatGPT subscription (no API key), slowly and safely.

    python ml/relabel_v5_codex.py --stage pass1 [--model gpt-6.1-sol] [--effort high] [--workers 3] [--limit 20]
    python ml/relabel_v5_codex.py --stage all          # pass1..passN, then nothing else: vote/audit are separate steps

Why this shape (2026-10-21): the first run opened up to 256 `codex exec` sessions at once; the subscription answered 429 and
Cloudflare 403, and 72% of the calls were thrown away because the model read the batch file with a tool.
- Few sessions at a time (--workers, default 3).
- Every call runs in its own empty temporary folder that holds only the instructions and that one batch. A model that uses a tool there can only see those two files, so a tool call is allowed and the pass stays independent. The batch is also in the prompt, so no tool is needed.
- On 429, 403, a usage-limit or rate-limit message, every worker pauses: 15 minutes, then 30, then 60 (the subscription's windows reset), and the call is retried without counting as an attempt.
- A finished batch is never redone; the command can be stopped and started again at any time.
- Format problems are retried in a new session with the problems listed (up to --retries).
Each call is logged to v5/runs.jsonl (transport codex-exec-isolated-dir).
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relabel_v5 as R, relabel_v5_gpt as G

LOCK = threading.Lock(); PAUSE = {"until": 0.0, "step": 0}
LIMIT = re.compile(r"429|too many requests|403|forbidden|usage limit|rate limit|quota|try again later", re.I)
FILES = {"pass": ["GUIDE_v5.md"], "adjudicate": ["GUIDE_v5.md", "ADJUDICATE.md"], "audit": ["GUIDE_v5.md", "AUDIT.md"]}


def kind(stage): return "pass" if stage.startswith("pass") else stage


def prompt(stage, items, feedback=None):
    p = ("You are one independent labeller. Everything you need is below and in the files of the current folder. "
         "Do not read, list or search any file outside the current folder, and do not run commands you do not need.\n\n"
         + G.instructions(stage) + "\n\n---\n\n" + G.ask(stage, items)
         + "\n\nYour final message must be only the JSON lines, with no code fence and no other text.")
    if feedback: p += "\n\nAn earlier answer to this same batch had these problems; avoid them:\n- " + "\n- ".join(feedback[:10])
    return p


def wait_if_paused():
    while True:
        with LOCK: left = PAUSE["until"] - time.time()
        if left <= 0: return
        time.sleep(min(left, 60))


def hit_limit(text):
    with LOCK:
        if PAUSE["until"] > time.time(): return
        PAUSE["step"] = min(PAUSE["step"] + 1, 3); minutes = [15, 30, 60][PAUSE["step"] - 1]
        PAUSE["until"] = time.time() + 60 * minutes
        print(time.strftime("%H:%M"), f"limit reached ({text[:120].strip()}); every worker pauses {minutes} min", flush=True)


def run_batch(a, f):
    stage = a.stage_now; out = R.V5 + f"{stage}/out/" + os.path.basename(f)[:-5] + ".jsonl"; os.makedirs(os.path.dirname(out), exist_ok=True)
    items = json.load(open(f, encoding="utf-8")); want = [(it.get("record") or it)["id"] for it in items]
    if os.path.exists(out) and not G.problems(stage, want, open(out, encoding="utf-8").read()): return "skip"
    feedback, attempt = None, 0
    while attempt < a.retries:
        wait_if_paused()
        tmp = tempfile.mkdtemp(prefix="adctox_v5_")
        try:
            for name in FILES[kind(stage)]:
                shutil.copy(R.P.REPO + "data/curated/concept_organs/GUIDE_v5.md" if name == "GUIDE_v5.md" else R.V5 + name, tmp)
            json.dump(items, open(os.path.join(tmp, "batch.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            last = os.path.join(tmp, "answer.txt")
            cmd = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "-s", "read-only", "-C", tmp,
                   "-m", a.model, "-c", f'model_reasoning_effort="{a.effort}"', "-o", last, "-"]
            t0 = time.time()
            try:
                p = subprocess.run(cmd, input=prompt(stage, items, feedback), capture_output=True, text=True, timeout=a.timeout)
                log, code = (p.stdout or "") + (p.stderr or ""), p.returncode
            except subprocess.TimeoutExpired: log, code = "timeout", -1
            text = open(last, encoding="utf-8").read() if os.path.exists(last) else ""
            text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
            if not text and LIMIT.search(log):                                  # the subscription said no: pause, do not count
                hit_limit(LIMIT.search(log).group(0) + " " + log[-200:]); rec = dict(ok=False, problems=["limit: " + log[-200:].strip()])
            else:
                attempt += 1
                try: bad = G.problems(stage, want, text) if text else [f"no answer (exit {code}): {log[-200:].strip()}"]
                except (ValueError, KeyError) as e: bad = [f"not JSON lines: {e}"]
                rec = dict(ok=not bad, problems=bad[:3])
                if not bad:
                    open(out, "w", encoding="utf-8").write(text + "\n")
                    with LOCK: PAUSE["step"] = 0
                feedback = bad
            with LOCK:
                open(R.V5 + "runs.jsonl", "a").write(json.dumps(dict(stage=stage, batch=os.path.basename(f), model=a.model, effort=a.effort, attempt=attempt,
                    seconds=round(time.time() - t0, 1), transport="codex-exec-isolated-dir", exit_code=code, timestamp_utc=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), **rec)) + "\n")
            if rec["ok"]: return "ok"
        finally: shutil.rmtree(tmp, ignore_errors=True)
    return "failed"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", required=True); ap.add_argument("--model", default="gpt-6.1-sol"); ap.add_argument("--effort", default="high")
    ap.add_argument("--workers", type=int, default=3); ap.add_argument("--retries", type=int, default=3); ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=3600); a = ap.parse_args()
    stages = [f"pass{k}" for k in range(1, R.layout()[0] + 1)] if a.stage == "all" else [a.stage]
    for st in stages:
        a.stage_now = st; files = sorted(glob.glob(R.V5 + f"{st}/in/*.json"))[: a.limit]; res = {}
        with ThreadPoolExecutor(a.workers) as ex:
            for n, s in enumerate(ex.map(lambda f: run_batch(a, f), files), 1):
                res[s] = res.get(s, 0) + 1
                if n % 25 == 0: print(time.strftime("%m-%d %H:%M"), st, f"{n}/{len(files)}", res, flush=True)
        print(json.dumps(dict(stage=st, batches=len(files), **res)), flush=True)


if __name__ == "__main__":
    main()
