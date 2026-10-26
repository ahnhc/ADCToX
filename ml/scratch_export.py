"""The from-scratch organ judge for the app (x2te: ml/scratch_judge.py + the evidence reader's table), as one bundle folder.

    ADC_RESEARCH_MODE=1 ADCTOX_LABELS=v51 ADCTOX_CACHE=<v5.1 cache> python ml/scratch_export.py \
        --judge <cache>/scratch_judge_x2ts8 --evidence <cache>/evidence_judge_ev2s8 --out <bundle>/ScratchJudge
    -> config.json, tokenizer.json, tokenizer_config.json   the encoder's architecture and tokenizer (BERT-base, trained here)
       weights.safetensors                                    encoder and output layers, fp16
       index.npz                                              name vectors (fp16) and the concept id of each name
       concepts.json                                          id -> [name, organs, "label" | "record"]: the v5.1 organ label, or
                                                              for a MONDO concept without one the evidence reader's organs
       judge.json                                             thresholds, the MONDO-first margin, provenance
Check: ml/scratch_runtime.py on the exported folder gives the same rows as scratch_judge.judge on the gold dev queries.
The evidence reader itself is not shipped: its organs for every MONDO concept are precomputed into concepts.json.
"""
import argparse, json, os, shutil, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

MONDO_FIRST = 0.02


def export(judge, evidence, out):
    import torch, linking_models as LM
    from safetensors.torch import save_file
    from build_linking_pools import read_obo
    judge, evidence = judge.rstrip("/") + "/", evidence.rstrip("/") + "/"
    cfg = json.load(open(judge + "calibration.json")); bb = cfg["backbone"].rstrip("/") + "/"; os.makedirs(out, exist_ok=True)
    for f in ("config.json", "tokenizer.json", "tokenizer_config.json"): shutil.copy(bb + f, os.path.join(out, f))
    sd = torch.load(judge + "model.pt", map_location="cpu")
    save_file({k: v.half().contiguous() for k, v in sd.items()}, os.path.join(out, "weights.safetensors"))
    Z = np.load(judge + "index.npz", allow_pickle=True); ids = [str(x) for x in Z["ids"]]
    np.savez(os.path.join(out, "index.npz"), E=Z["E"].astype(np.float16), ids=np.array(ids))
    import scratch_judge as SJ
    labels, _ = LM.load_organ_labels(); T = read_obo(); AX = SJ.AXES
    E = np.load(evidence + "pred.npz", allow_pickle=True); thr = np.array(json.load(open(evidence + "calibration.json"))["thr"])
    ev = {str(i): [AX[a] for a in np.where(p >= thr)[0]] for i, p in zip(E["ids"], E["p"].astype(np.float32))}
    concepts = {}
    for c in sorted(set(ids)):
        lo = sorted(labels.get(c, []), key=AX.index)
        if lo: concepts[c] = [T[c]["name"], lo, "label"]
        elif ev.get(c): concepts[c] = [T[c]["name"], ev[c], "record"]
        else: concepts[c] = [T.get(c, {}).get("name", c), [], ""]
    json.dump(concepts, open(os.path.join(out, "concepts.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    j = dict(axes=AX, temp=cfg["temp"], thr=cfg["thr"], vthr=cfg["vthr"], theta=cfg["theta"], maxlen=cfg["maxlen"], mondo_first=MONDO_FIRST,
             judge=os.path.basename(judge.rstrip("/")), evidence=os.path.basename(evidence.rstrip("/")), backbone=cfg.get("revision"),
             labels=os.environ.get("ADCTOX_LABELS", "v4"))
    json.dump(j, open(os.path.join(out, "judge.json"), "w"), indent=1)
    print(f"-> {out}: {len(ids):,} names, {len(concepts):,} concepts "
          f"({sum(v[2] == 'label' for v in concepts.values()):,} labelled, {sum(v[2] == 'record' for v in concepts.values()):,} from the record)")


def check(judge, evidence, out):
    """the exported folder against the research code on the gold dev queries (organs, concept, validity)."""
    import eval_a4 as E4, eval_linking as EL, scratch_judge as SJ, scratch_runtime as SR
    Q, _, groups, _ = E4.gold(); texts = [q["query"] for i, q in enumerate(Q) if EL.split_of(groups[i]) == "dev"]
    os.environ["EVIDENCE_DIR"] = evidence; os.environ["MONDO_FIRST"] = str(MONDO_FIRST)
    a = SJ.judge(texts, judge.rstrip("/") + "/"); b = SR.judge(texts, out)
    same = [(x["concept"], sorted(x["organs"])) == (y["concept"], sorted(y["organs"])) for x, y in zip(a, b)]
    print(f"check: {sum(same)}/{len(same)} gold dev queries give the same concept and organs")
    for t, x, y, s in zip(texts, a, b, same):
        if not s: print(f"  {t!r}: research {x['concept']} {x['organs']} | app {y['concept']} {y['organs']}")
    return sum(same) / len(same)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--judge", required=True); ap.add_argument("--evidence", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--check-only", action="store_true"); a = ap.parse_args()
    if not a.check_only: export(a.judge, a.evidence, a.out)
    check(a.judge, a.evidence, a.out)
