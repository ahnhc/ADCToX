"""Tune Gemma with this repository's pipeline and data, then compare it with the untuned Gemma on the fixed benchmark.
One command, so anyone with the repository, a GPU and access to google/gemma-4-E2B can see what the tuning adds.

    ADC_RESEARCH_MODE=1 python ml/reproduce_judge.py --work /path/to/work_cache --tag r1 --stage "S1 ..." --note "..." \
        [--seeds 7,8,9] [--gpus 0,1] [--drop external,ko2] [--compare-to v5s7] [--app] [--test]

--work      a copy of the models cache (`adctox --update-models` writes one; copy it, never the live folder): the MONDO index
            and the label tables. Training writes its checkpoints into it. Refused when it is the live cache.
Per seed:   ml/gemma_judge2.py (training, pre-training checks, run card <tag>s<seed>) -> ml/gemma_export.py (int8 folder)
            -> ml/bench_judge.py --system single (scores on the card); --app also scores the full app pipeline with it.
Once:       ml/bench_judge.py --system base (the untuned Gemma; reused while the base revision and the questions are the same).
Report:     ml/results/reproduce/<tag>.md: base vs each seed and the seed mean, organ F1 per organ against TARGET, Korean and
            English, invalid inputs, with paired bootstrap intervals; and the ledger (ml/docs/tuning_log.md) is re-rendered.
Dev unless --test. Look at test once, at the end of the tuning.
"""
import argparse, json, os, subprocess, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

TARGET = 0.95                      # organ F1, each of the 13 organs
PY = sys.executable
LIVE = os.path.realpath(os.environ.get("ADCTOX_LIVE_CACHE", "/data/hyeongchanahn/adctox/ml_cache"))


def sh(cmd, env, log):
    print("  $", " ".join(cmd), "->", log, flush=True)
    with open(log, "w") as fh:
        r = subprocess.run(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT, cwd=P.REPO)
    if r.returncode: raise SystemExit(f"failed ({r.returncode}): {' '.join(cmd)}; see {log}")


def farm(work, name):
    """a folder that links every file of the work cache except GemmaJudge, for one exported model."""
    d = os.path.join(os.path.dirname(work.rstrip("/")), f"{os.path.basename(work.rstrip('/'))}_{name}")
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(work):
        if f == "GemmaJudge" or f.startswith("gemma_judge2_"): continue
        dst = os.path.join(d, f)
        if not os.path.lexists(dst): os.symlink(os.path.realpath(os.path.join(work, f)), dst)
    return d


def run_seed(a, seed, gpu, logs):
    tag = f"{a.tag}s{seed}"; env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), ADC_RESEARCH_MODE="1", ADCTOX_CACHE=a.work)
    cmd = [PY, "ml/gemma_judge2.py", "--tag", tag, "--seed", str(seed), "--stage", a.stage, "--note", a.note, "--layers", str(a.layers),
           "--rank", str(a.rank), "--epochs", str(a.epochs), "--lr", str(a.lr), "--consist", str(a.consist), "--clip", str(a.clip)]
    if a.drop: cmd += ["--drop", a.drop]
    if a.compare_to: cmd += ["--compare-to", f"{a.compare_to}"]
    if not (a.resume and os.path.exists(os.path.join(a.work, f"gemma_judge2_{tag}", "calibration.npz"))): sh(cmd, env, f"{logs}/train_{tag}.log")
    out = farm(a.work, tag)
    sh([PY, "ml/gemma_export.py", "--v2", "--tag", tag, "--layers", str(a.layers), "--rank", str(a.rank), "--out", os.path.join(out, "GemmaJudge")], env, f"{logs}/export_{tag}.log")
    subprocess.run(["git", "checkout", "ml/results/benchmarks/gemma_export.json"], cwd=P.REPO, capture_output=True)
    env = dict(env, ADCTOX_CACHE=out)
    sh([PY, "ml/bench_judge.py", "--system", "single", "--name", f"single_{tag}", "--card", tag], env, f"{logs}/bench_single_{tag}.log")
    if a.app: sh([PY, "ml/bench_judge.py", "--system", "app", "--name", f"app_{tag}", "--card", tag], env, f"{logs}/bench_app_{tag}.log")
    return tag


def base_name():
    """the untuned-Gemma benchmark of the Gemma size in use (GEMMA_MODEL): bench_base for E2B, bench_base_e4b for E4B, ..."""
    import gemma_judge as GJ
    return "base" if GJ.GEMMA == "google/gemma-4-E2B" else "base_" + GJ.GEMMA.rsplit("-", 1)[-1].lower()


def base_current():
    import gemma_judge as GJ, bench_judge as B
    p = B.OUT + f"bench_{base_name()}.json"
    if not os.path.exists(p): return False
    b = json.load(open(p)); return b.get("revision") == GJ.REV and b.get("questions") == B.questions_sha()


def report(a, tags):
    import bench_judge as B, eval_linking as EL
    split = "test" if a.test else "dev"; Q, gold, groups, ko, SE = B.questions(); ix = [i for i, g in enumerate(groups) if EL.split_of(g) == split]
    load = lambda n: json.load(open(B.OUT + f"bench_{n}.json"))["per"]
    systems = [base_name()] + [f"single_{t}" for t in tags] + ([f"app_{t}" for t in tags] if a.app else [])
    per = {n: load(n) for n in systems}
    def organ_f1(rows, lang):
        jx = [i for i in ix if rows[lang][i] is not None]
        m = EL.metrics([((r or {}).get("concept"), (r or {}).get("organs", [])) for r in rows[lang]], gold, jx); return m
    L = [f"# 재현 결과: {a.tag}", "", f"- 단계: {a.stage}", f"- 메모: {a.note}", f"- 분할: {split}", f"- seed: {a.seeds}",
         f"- 뺀 데이터: {a.drop or '없음'}", f"- 만든 시각: {time.strftime('%Y-%m-%d %H:%M')}", "",
         "## 튜닝 안 한 Gemma와 비교", "", "| 시스템 | 영어 장기 F1 | 한국어 장기 F1 | 영어 개념 | 한국어 개념 | 무효 수락 | 영어 Δ vs base [95%] | 한국어 Δ vs base [95%] |", "|---|---|---|---|---|---|---|---|"]
    M = {}
    for n in systems:
        r = {lang: organ_f1(per[n], lang) for lang in ("en", "ko")}; M[n] = r; d = []
        for lang in ("en", "ko"):
            if n == systems[0]: d.append("–"); continue
            jx = [i for i in ix if per[n][lang][i] is not None and per[systems[0]][lang][i] is not None]
            pa = [((x or {}).get("concept"), (x or {}).get("organs", [])) for x in per[n][lang]]; pb = [((x or {}).get("concept"), (x or {}).get("organs", [])) for x in per[systems[0]][lang]]
            b = EL.boot(pa, pb, gold, jx, groups); d.append(f"{b['delta']:+.3f} [{b['lo']:+.3f}, {b['hi']:+.3f}]")
        f = lambda v: "–" if v is None else f"{v:.3f}"
        L.append(f"| {n} | {f(r['en']['macro_f1'])} | {f(r['ko']['macro_f1'])} | {f(r['en']['concept_acc'])} | {f(r['ko']['concept_acc'])} | {f(r['en']['false_accept_invalid'])} | {d[0]} | {d[1]} |")
    singles = [f"single_{t}" for t in tags]
    L += ["", f"## 장기별 F1 (목표: 모든 장기 {TARGET} 이상)", "", "seed 평균. ✓는 목표 이상.", "",
          "| 장기 | base 영어 | base 한국어 | 튜닝 영어 | 튜닝 한국어 |", "|---|---|---|---|---|"]
    axes = B.AXES; met = {"en": 0, "ko": 0}
    for ax in axes:
        cell = []
        for n, lang in ((systems[0], "en"), (systems[0], "ko")): cell.append(M[n][lang]["per_organ_f1"][ax])
        for lang in ("en", "ko"):
            v = [M[n][lang]["per_organ_f1"][ax] for n in singles if M[n][lang]["per_organ_f1"][ax] is not None]
            m = float(np.mean(v)) if v else None; cell.append(m); met[lang] += m is not None and m >= TARGET
        L.append(f"| {ax} | " + " | ".join("–" if c is None else f"{c:.2f}" + (" ✓" if k >= 2 and c >= TARGET else "") for k, c in enumerate(cell)) + " |")
    L += ["", f"목표를 넘은 장기: 영어 {met['en']}/13, 한국어 {met['ko']}/13.", "",
          "장기별 dev 양성 수가 9~85개라 한두 개 차이로 F1이 0.05씩 움직인다. 목표 판정은 seed 평균과 test 한 번으로 한다.", ""]
    os.makedirs(P.REPO + "ml/results/reproduce", exist_ok=True); p = P.REPO + f"ml/results/reproduce/{a.tag}.md"
    open(p, "w", encoding="utf-8").write("\n".join(L) + "\n"); print("\n".join(L)); print("->", p)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--work", required=True); ap.add_argument("--tag", required=True)
    ap.add_argument("--stage", required=True); ap.add_argument("--note", default=""); ap.add_argument("--seeds", default="7,8,9")
    ap.add_argument("--gpus", default="0"); ap.add_argument("--drop", default=""); ap.add_argument("--compare-to", default=None)
    ap.add_argument("--layers", type=int, default=18); ap.add_argument("--rank", type=int, default=16); ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-4); ap.add_argument("--consist", type=float, default=0.0); ap.add_argument("--clip", type=float, default=0.0); ap.add_argument("--app", action="store_true"); ap.add_argument("--test", action="store_true")
    ap.add_argument("--report-only", action="store_true"); ap.add_argument("--resume", action="store_true", help="skip training for seeds whose checkpoint exists")
    a = ap.parse_args(); a.work = os.path.realpath(a.work)
    import adc_runtime as RT
    live = {LIVE, os.path.realpath(str(RT.model_home()))}
    if a.work in live or any(a.work.startswith(x + os.sep) for x in live): raise SystemExit("--work is a live models folder; copy it and pass the copy")
    if not os.path.exists(os.path.join(a.work, "mondo_index.npz")): raise SystemExit(f"{a.work} has no mondo_index.npz (not a models cache)")
    logs = P.REPO + f"ml/results/reproduce/logs_{a.tag}"; os.makedirs(logs, exist_ok=True)
    seeds = [int(s) for s in a.seeds.split(",")]; gpus = a.gpus.split(","); tags = [f"{a.tag}s{s}" for s in seeds]
    if not a.report_only:
        if not base_current():
            print("untuned Gemma: benchmark", flush=True)
            sh([PY, "ml/bench_judge.py", "--system", "base", "--name", base_name()], dict(os.environ, CUDA_VISIBLE_DEVICES=gpus[0], ADCTOX_CACHE=a.work), f"{logs}/bench_base.log")
        import queue
        from concurrent.futures import ThreadPoolExecutor
        free = queue.Queue()
        for g in gpus: free.put(g)
        def job(s):                                                          # one seed per GPU at a time
            g = free.get()
            try: return run_seed(a, s, g, logs)
            finally: free.put(g)
        with ThreadPoolExecutor(len(gpus)) as ex:
            for f in [ex.submit(job, s) for s in seeds]: f.result()
    report(a, tags)
    import tuning_ledger as TL; TL.render()


if __name__ == "__main__":
    main()
