"""A small GPU job queue for long tuning sweeps: one job per GPU at a time, jobs taken in file order.

    python ml/gpu_queue.py --queue <jobs.txt> --gpus 1,2,3 [--log-dir <dir>]

jobs.txt: one shell command per line ("#" lines are skipped). A taken job is moved to <jobs.txt>.done with its GPU, start and end
time and exit code, so lines can be appended to jobs.txt while the queue runs. Each job gets CUDA_VISIBLE_DEVICES set to its GPU
and its output in <log-dir>/<n>.log. The queue stops taking jobs when <jobs.txt>.stop exists, and exits when jobs.txt is empty
and nothing runs.
"""
import argparse, fcntl, os, subprocess, time


def take(path):
    with open(path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX); lines = f.read().splitlines(); job, rest = None, []
        for l in lines:
            if job is None and l.strip() and not l.lstrip().startswith("#"): job = l
            else: rest.append(l)
        f.seek(0); f.truncate(); f.write("\n".join(rest) + ("\n" if rest else ""))
    return job


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--queue", required=True); ap.add_argument("--gpus", default="1,2,3")
    ap.add_argument("--log-dir", default=None); a = ap.parse_args()
    logs = a.log_dir or a.queue + ".logs"; os.makedirs(logs, exist_ok=True); running, n = {}, len(os.listdir(logs))
    while True:
        for g, (p, job, t0, k) in list(running.items()):
            if p.poll() is not None:
                open(a.queue + ".done", "a").write(f"[gpu {g}] {time.strftime('%m-%d %H:%M', time.localtime(t0))} -> {time.strftime('%m-%d %H:%M')} exit {p.returncode} log {k}: {job}\n")
                del running[g]
        if not os.path.exists(a.queue + ".stop"):
            for g in a.gpus.split(","):
                if g in running: continue
                job = take(a.queue)
                if not job: break
                n += 1; log = f"{logs}/{n:03d}.log"
                p = subprocess.Popen(["bash", "-c", job], env=dict(os.environ, CUDA_VISIBLE_DEVICES=g), stdout=open(log, "w"), stderr=subprocess.STDOUT)
                running[g] = (p, job, time.time(), log)
        if not running and (os.path.exists(a.queue + ".stop") or not any(l.strip() and not l.lstrip().startswith("#") for l in open(a.queue))): break
        time.sleep(30)


if __name__ == "__main__":
    main()
