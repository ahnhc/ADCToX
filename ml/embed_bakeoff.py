"""Embed the same 2,732 disease / outcome strings with several encoders, for the embedding bake-off.
Each model -> $CACHE/emb_<name>.npz {keys, emb(L2-normalised)}.  A model that fails to load is skipped, not fatal."""
import sys, os, numpy as np, torch, warnings, traceback
warnings.filterwarnings("ignore")
C = "/data/hyeongchanahn/adctox/ml_cache/"
keys = list(np.load(C + "sapbert.npz", allow_pickle=True)["keys"])
which = sys.argv[1:] or ["biolord", "pubmedbert", "medcpt", "bge_m3", "qwen3_0.6b"]

@torch.no_grad()
def hf_pool(name, pool, bs=128, prefix=""):
    from transformers import AutoTokenizer, AutoModel
    tok = AutoTokenizer.from_pretrained(name); mod = AutoModel.from_pretrained(name, torch_dtype=torch.float16).cuda().eval(); out = []
    for i in range(0, len(keys), bs):
        b = tok([prefix + k for k in keys[i:i + bs]], padding=True, truncation=True, max_length=64, return_tensors="pt").to("cuda")
        h = mod(**b).last_hidden_state.float()
        if pool == "cls": out.append(h[:, 0].cpu().numpy())
        else: m = b["attention_mask"].unsqueeze(-1).float(); out.append(((h * m).sum(1) / m.sum(1)).cpu().numpy())
    return np.concatenate(out)

@torch.no_grad()
def st(name, bs=128):
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(name, device="cuda", model_kwargs={"torch_dtype": torch.float16}); return m.encode(keys, batch_size=bs, normalize_embeddings=True, convert_to_numpy=True)

SPEC = {"biolord": lambda: st("FremyCompany/BioLORD-2023"),
        "pubmedbert": lambda: hf_pool("microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext", "mean"),
        "medcpt": lambda: hf_pool("ncbi/MedCPT-Article-Encoder", "cls"),
        "bge_m3": lambda: st("BAAI/bge-m3"),
        "qwen3_0.6b": lambda: st("Qwen/Qwen3-Embedding-0.6B"),
        "qwen3_4b": lambda: st("Qwen/Qwen3-Embedding-4B", bs=32)}
import time
def with_retry(fn):
    for _ in range(60):
        try: return fn()
        except (torch.OutOfMemoryError, RuntimeError) as e:
            if not any(k in str(e) for k in ("CUBLAS", "CUDNN", "out of memory", "CUDA error")): raise
            torch.cuda.empty_cache(); time.sleep(30)
    raise RuntimeError("GPU stayed full")
for n in which:
    try:
        E = with_retry(SPEC[n]).astype(np.float32); E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
        np.savez(C + f"emb_{n}.npz", keys=np.array(keys, dtype=object), emb=E); print("ok", n, E.shape, flush=True)
    except Exception as e: print("FAILED", n, repr(e)[:200], flush=True)
