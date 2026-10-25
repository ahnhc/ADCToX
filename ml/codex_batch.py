"""Run a folder of JSON batches through `codex exec` (ChatGPT subscription), safely: the generic form of ml/relabel_v5_codex.py.

    python ml/codex_batch.py --dir <task_dir> [--workers 3] [--model gpt-6.1-sol] [--effort high]

<task_dir>/TASK.md       instructions for one batch (the prompt; it is also copied into the call's folder)
<task_dir>/files/*       other files the instructions refer to (copied next to the batch)
<task_dir>/in/<b>.json   a list of items, each with "id" (or record.id)
<task_dir>/out/<b>.jsonl the answer: one JSON line per item, same ids in the same order (checked; retried with the problems listed)
Every call runs in its own empty temporary folder that holds only TASK.md, files/* and batch.json. On 429/403/usage-limit
messages every worker pauses 15, 30, then 60 minutes, without counting an attempt. Finished batches are skipped. Calls are
logged to <task_dir>/runs.jsonl.
"""
import argparse, glob, json, os, re, shutil, subprocess, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor

LOCK = threading.Lock(); PAUSE = {"until": 0.0, "step": 0}
LIMIT = re.compile(r"429|too many requests|403|forbidden|usage limit|rate limit|quota|try again later", re.I)


def ids_of(items): return [(it.get("record") or it)["id"] for it in items]


def jsonl(text): return "\n".join(l.strip() for l in text.splitlines() if l.strip().startswith("{"))   # drop any prose around the lines


def problems(want, text):
    try: rows = [json.loads(l) for l in jsonl(text).splitlines()]
    except ValueError as e: return [f"not JSON lines: {e}"]
    if [r.get("id") for r in rows] != want: return [f"expected {len(want)} lines with ids in this order: {want}"]
    err = [r["id"] for r in rows if "error" in r]
    return [f"lines with an error instead of an answer: {err[:5]}; every file you need is pasted in the prompt"] if err else []


def wait_if_paused():
    while True:
        with LOCK: left = PAUSE["until"] - time.time()
        if left <= 0: return
        time.sleep(min(left, 60))


def hit_limit(text):
    with LOCK:
        if PAUSE["until"] > time.time(): return
        PAUSE["step"] = min(PAUSE["step"] + 1, 3); m = [15, 30, 60][PAUSE["step"] - 1]; PAUSE["until"] = time.time() + 60 * m
        print(time.strftime("%H:%M"), f"limit reached ({text[:120].strip()}); every worker pauses {m} min", flush=True)


def run_batch(a, f):
    d = a.dir; out = f"{d}/out/" + os.path.basename(f)[:-5] + ".jsonl"; os.makedirs(os.path.dirname(out), exist_ok=True)
    items = json.load(open(f, encoding="utf-8")); want = ids_of(items)
    if os.path.exists(out) and not problems(want, open(out, encoding="utf-8").read()): return "skip"
    task = open(f"{d}/TASK.md", encoding="utf-8").read(); feedback, attempt = None, 0
    for g in sorted(glob.glob(f"{d}/files/*")):                                          # the files are pasted too: reading them can fail in the sandbox
        task += f"\n\n---\n\n# File {os.path.basename(g)}\n\n" + open(g, encoding="utf-8").read()
    while attempt < a.retries:
        wait_if_paused(); tmp = tempfile.mkdtemp(prefix="adctox_cb_")
        try:
            shutil.copy(f"{d}/TASK.md", tmp)
            for g in glob.glob(f"{d}/files/*"): shutil.copy(g, tmp)
            json.dump(items, open(os.path.join(tmp, "batch.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            prompt = ("You are one independent reviewer. Everything you need is below and in the files of the current folder. Do not read "
                      "any file outside the current folder.\n\n" + task + f"\n\n---\n\nThe batch ({len(items)} items, also in batch.json):\n"
                      + json.dumps(items, ensure_ascii=False, indent=1) + f"\n\nYour final message must be only the {len(items)} JSON lines, no code fence, no other text.")
            if feedback: prompt += "\n\nAn earlier answer to this batch had these problems; avoid them:\n- " + "\n- ".join(feedback[:5])
            last = os.path.join(tmp, "answer.txt"); t0 = time.time()
            cmd = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "-s", "read-only", "-C", tmp,
                   "-m", a.model, "-c", f'model_reasoning_effort="{a.effort}"', "-o", last, "-"]
            try:
                p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=a.timeout); log, code = (p.stdout or "") + (p.stderr or ""), p.returncode
            except subprocess.TimeoutExpired: log, code = "timeout", -1
            text = open(last, encoding="utf-8").read() if os.path.exists(last) else ""
            text = jsonl(text)
            if not text and LIMIT.search(log): hit_limit(LIMIT.search(log).group(0) + " " + log[-200:]); rec = dict(ok=False, problems=["limit"])
            else:
                attempt += 1; bad = problems(want, text) if text else [f"no answer (exit {code}): {log[-200:].strip()}"]; rec = dict(ok=not bad, problems=bad[:3])
                if not bad:
                    open(out, "w", encoding="utf-8").write(text + "\n")
                    with LOCK: PAUSE["step"] = 0
                feedback = bad
            with LOCK:
                open(f"{d}/runs.jsonl", "a").write(json.dumps(dict(batch=os.path.basename(f), model=a.model, effort=a.effort, attempt=attempt, seconds=round(time.time() - t0, 1),
                                                                    transport="codex-exec-isolated-dir", exit_code=code, timestamp_utc=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), **rec)) + "\n")
            if rec["ok"]: return "ok"
        finally: shutil.rmtree(tmp, ignore_errors=True)
    return "failed"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", required=True); ap.add_argument("--model", default="gpt-6.1-sol"); ap.add_argument("--effort", default="high")
    ap.add_argument("--workers", type=int, default=3); ap.add_argument("--retries", type=int, default=3); ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args(); a.dir = a.dir.rstrip("/"); files = sorted(glob.glob(f"{a.dir}/in/*.json")); res = {}
    with ThreadPoolExecutor(a.workers) as ex:
        for n, s in enumerate(ex.map(lambda f: run_batch(a, f), files), 1):
            res[s] = res.get(s, 0) + 1
            if n % 10 == 0: print(time.strftime("%m-%d %H:%M"), f"{n}/{len(files)}", res, flush=True)
    print(json.dumps(dict(dir=a.dir, batches=len(files), **res)), flush=True)


if __name__ == "__main__":
    main()
