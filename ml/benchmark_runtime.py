"""Runtime benchmark of the whole free-text path the terminal runs (linking + FinnGen MLP + ADC ordering).

    python -I ml/benchmark_runtime.py --device cpu --out ml/results/benchmarks/runtime_<tag>_cpu.json
    python -I ml/benchmark_runtime.py --device cuda --out ml/results/benchmarks/runtime_<tag>_cuda.json

Per query it does what the wizard does: analyze_conditions([q]) (BioLORD registry search, SapBERT/MONDO link, MLP),
then recommend([q]) with the 'auto' fallback. Measured: cold start (fresh process, import + first query), warm cache miss
(new text, models already loaded), warm cache hit (same text again), peak RSS and peak VRAM. Outputs (organs, estimates,
ADC order) are saved so two code versions can be checked for identical results. UI drawing is not included.
"""
import argparse, json, os, resource, statistics, subprocess, sys, time

QUERIES = ["lung hole", "xqzv blorp", "diabetic nephropathy", "asthma", "atrial fibrillation", "hypertension", "rheumatoid arthritis",
           "lupus nephritis", "chronic kidney disease stage 4", "epilepsy", "parkinson disease", "psoriatic arthritis", "gout",
           "hepatitis b", "alcoholic liver disease", "crohn disease", "celiac disease", "macular degeneration", "uveitis",
           "tinnitus", "osteoporosis", "sarcoidosis", "pulmonary hypertension", "deep vein thrombosis", "stroke", "migraine",
           "hyperthyroidism", "cushing syndrome", "sickle cell disease", "hemophilia", "myasthenia gravis", "bronchiectasis",
           "sleep apnea", "eczema", "vitiligo", "glomerulonephritis", "polycystic kidney", "heart attack", "weak heart", "sugar diabetes"]


def one(q):
    import recommend as RC
    rep = RC.analyze_conditions([q])
    RC.FALLBACK = {c: 0.25 for c in RC.unresolved([q])}
    rows, s, notes, _ = RC.recommend([q])
    RC.FALLBACK = {}
    r = rep[0] if rep else {}
    return dict(query=q, source=r.get("source"), name=r.get("name"), organs=r.get("organs"),
                estimates=[[a, round(v, 4)] for a, v in r.get("estimates", [])], s=s, order=[[x["rank"], x["adc"]] for x in rows])


def peak_vram():
    try:
        import torch
        return torch.cuda.max_memory_allocated() / 2**20 if torch.cuda.is_available() else None
    except Exception:
        return None


def child(query):
    t0 = time.perf_counter()
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    import recommend  # noqa: F401
    t1 = time.perf_counter(); one(query); t2 = time.perf_counter()
    print(json.dumps(dict(import_s=t1 - t0, first_query_s=t2 - t1, total_s=t2 - t0,
                          peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, peak_vram_mb=peak_vram())))


def pct(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p / 100; f = int(k); return xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu"); ap.add_argument("--cold", type=int, default=3)
    ap.add_argument("--out", required=True); ap.add_argument("--child"); a = ap.parse_args()
    if a.child is not None: return child(a.child)
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", ADC_RESEARCH_MODE="1")
    if a.device == "cpu": env["CUDA_VISIBLE_DEVICES"] = ""
    os.environ.update(env)
    cold = []
    for i in range(a.cold):
        p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "--child", QUERIES[i % len(QUERIES)], "--out", "-"], env=env, capture_output=True, text=True)
        cold.append(json.loads(p.stdout.strip().splitlines()[-1]))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import recommend  # noqa: F401
    import torch
    t = time.perf_counter(); one("warm-up condition"); warmup = time.perf_counter() - t
    miss, outs = [], []
    for q in QUERIES:
        t = time.perf_counter(); outs.append(one(q)); miss.append(time.perf_counter() - t)
    hit = []
    for q in QUERIES:
        t = time.perf_counter(); one(q); hit.append(time.perf_counter() - t)
    summ = lambda xs: dict(p50=statistics.median(xs), p95=pct(xs, 95), mean=statistics.mean(xs), n=len(xs))
    res = dict(device=a.device, torch=torch.__version__, threads=torch.get_num_threads(),
               gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
               cold=dict(runs=cold, first_query_p50=statistics.median([c["first_query_s"] for c in cold]), total_p50=statistics.median([c["total_s"] for c in cold])),
               warmup_s=warmup, warm_miss=summ(miss), warm_hit=summ(hit),
               peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, peak_vram_mb=peak_vram(), outputs=outs)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True); json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "outputs"}, indent=1))


if __name__ == "__main__":
    main()
