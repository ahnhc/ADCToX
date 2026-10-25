"""Teacher outputs for distilling the tuned Gemma judges into the from-scratch judge (X2, ml/scratch_judge.py --distill).

    CUDA_VISIBLE_DEVICES=2 ADC_RESEARCH_MODE=1 ADCTOX_LABELS=v51 ADCTOX_CACHE=<work cache with gemma_judge2_<tag>/> \
        python ml/distill_teacher.py --tags v51as7,v51as8,v51as9 --out /data/hyeongchanahn/adctox/work/distill/teacher_v51.npz

Texts (one per normalised string): every MONDO name and synonym of a non-obsolete concept, the UMLS names linked to MONDO
(ml/umls_build.py items), and every HPO term name and synonym. Left out: names of gold concepts and their parents and children
(LM.gold_held), and every evaluation question (TL.eval_concepts, known_eval questions), so the student never sees an evaluation
input through the teacher.
Teacher: each tag's float Gemma judge (backbone + LoRA + heads from $ADCTOX_CACHE/gemma_judge2_<tag>/), on the GPU; organ
probabilities use each judge's calibrated temperatures; the tags are averaged.
-> npz: texts, source, organ (n x 13, float16), valid (n, float16), tags.
"""
import argparse, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P


def texts(umls_all=False):
    import linking_models as LM, tuning_ledger as TL, known_eval as KE
    from build_linking_pools import read_obo
    T = read_obo(); held = LM.gold_held(T); ev = set(TL.eval_concepts())
    for lg, qs in KE.questions().items(): ev |= {TL.norm(q["text"]) for q in qs}
    held_names = {TL.norm(n) for t in held if t in T for n in [T[t]["name"]] + T[t]["syn"]}; out = {}
    def add(t, src):
        k = TL.norm(t)
        if t and k and k not in ev and k not in held_names and k not in out: out[k] = (t.strip(), src)
    for t, x in T.items():
        if t in held or x["name"].startswith("obsolete"): continue
        for n in [x["name"]] + x["syn"]: add(n, "mondo")
    um = P.REPO + "data/curated/external/umls/items.jsonl"
    if os.path.exists(um):
        for r in map(json.loads, open(um, encoding="utf-8")):
            if r.get("mondo") not in held: add(r["text"], "umls")
    if umls_all:                                                                         # every English level-0 name of a UMLS Disorders concept
        import umls_build as UB
        meta = "/data/hyeongchanahn/adctox/raw/umls/2026AA/META/"
        sab0 = {f[3] for f in (l.split("|") for l in open(meta + "MRSAB.RRF", encoding="utf-8")) if f[13] == "0"}
        diso = {f[0] for f in (l.split("|") for l in open(meta + "MRSTY.RRF", encoding="utf-8")) if f[1] in UB.DISO_TUIS}
        xref = UB.mondo_xrefs(os.path.join(P.REPO, "data/raw_big/mondo/2026-10-07/mondo.obo")); names = {}
        for l in open(meta + "MRCONSO.RRF", encoding="utf-8"):
            f = l.split("|")
            if f[0] in diso and f[11] in sab0 and f[1] == "ENG" and f[16] == "N" and len(f[14]) <= 100: names.setdefault(f[0], []).append(f[14])
        for c, ns in names.items():
            if xref.get(c, set()) & held or any(TL.norm(n) in held_names for n in ns): continue
            for n in list(dict.fromkeys(ns))[:8]: add(n, "umls_diso")
    cur = None
    for l in open(P.REPO + "data/raw/hpo/hp.obo", encoding="utf-8"):
        l = l.rstrip("\n")
        if l == "[Term]": cur = []
        elif l.startswith("["): cur = None
        elif cur is not None and l.startswith("name: "): add(l[6:], "hpo")
        elif cur is not None and l.startswith("synonym: "): add(l.split('"')[1], "hpo")
    return [v[0] for v in out.values()], [v[1] for v in out.values()]


def teacher(tag, X):
    import torch, gemma_judge as GJ, gemma_judge2 as G2
    from peft import get_peft_model, LoraConfig
    d = P.CACHE + f"gemma_judge2_{tag}/"; info = json.load(open(d + "info.json")); cal = np.load(d + "calibration.npz")
    import tuning_ledger as TL
    card = json.load(open(TL.CARDS + f"{tag}.json")) if os.path.exists(TL.CARDS + f"{tag}.json") else {}
    args = card.get("args", {}); layers, rank = args.get("layers", 18), args.get("rank", 16)
    tok, lm, _ = GJ.load_backbone(layers); tok.padding_side = "right"
    lm = get_peft_model(lm, LoraConfig(r=rank, lora_alpha=2 * rank, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    model = G2.Judge2(lm, lm.config.hidden_size, len(info["profiles"])).to(G2.DEV)
    missing = model.load_state_dict(torch.load(d + "adapter_head.pt", map_location=G2.DEV), strict=False)
    assert not [k for k in missing.missing_keys if "lora" in k or not k.startswith("lm.")], "adapter/head weights missing"
    zo, zv, _, _ = G2.predict(model, tok, X, bs=256)
    organ = 1 / (1 + np.exp(-zo / cal["temp"])); valid = 1 / (1 + np.exp(-zv))
    del model, lm; torch.cuda.empty_cache(); return organ, valid


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tags", required=True); ap.add_argument("--out", required=True); ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--umls-all", action="store_true", help="also every English name of UMLS Disorders concepts (not only those linked to MONDO)")
    a = ap.parse_args(); X, S = texts(a.umls_all)
    if a.limit: X, S = X[:a.limit], S[:a.limit]
    print(dict(texts=len(X), by_source={s: S.count(s) for s in set(S)}), flush=True)
    O, V = [], []
    for t in a.tags.split(","):
        o, v = teacher(t, X); O.append(o); V.append(v); print(t, "done; mean organs >= 0.5:", round(float((o >= 0.5).sum(1).mean()), 3), "valid >= 0.5:", round(float((v >= 0.5).mean()), 3), flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    np.savez(a.out, texts=np.array(X), source=np.array(S), organ=np.mean(O, 0).astype(np.float16), valid=np.mean(V, 0).astype(np.float16), tags=np.array(a.tags.split(",")))
    print("->", a.out, flush=True)


if __name__ == "__main__":
    main()
