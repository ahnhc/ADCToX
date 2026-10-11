"""Embed every disease / adverse-event string with SapBERT (UMLS-aligned biomedical encoder).

Output: one .npz per source in $CACHE, keyed by the exact string, so the two tasks share it.
"""
import sys, os, numpy as np, pandas as pd, torch, warnings
from transformers import AutoTokenizer, AutoModel
warnings.filterwarnings("ignore")
CACHE = "/data/hyeongchanahn/adctox/ml_cache"
SRC = "/data/hyeongchanahn/adctox/ml_cache/"
NAME = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"

def texts():
    f = pd.read_parquet(SRC + "finngen.parquet")
    t = pd.read_pickle(SRC + "tox.pkl")
    s = set(f.prior_longname.dropna()) | set(f.outcome_longname.dropna()) | set(t["Raw AE term"].dropna().astype(str))
    return sorted(x.strip() for x in s if x.strip())

@torch.no_grad()
def embed(strs, bs=256):
    tok = AutoTokenizer.from_pretrained(NAME); mod = AutoModel.from_pretrained(NAME).cuda().half().eval()
    out = []
    for i in range(0, len(strs), bs):
        b = tok(strs[i:i+bs], padding=True, truncation=True, max_length=48, return_tensors="pt").to("cuda")
        out.append(mod(**b).last_hidden_state[:, 0].float().cpu().numpy())   # [CLS], SapBERT's recommended pooling
    return np.concatenate(out)

if __name__ == "__main__":
    s = texts(); print("unique strings", len(s))
    E = embed(s); E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
    np.savez(f"{CACHE}/sapbert.npz", keys=np.array(s, dtype=object), emb=E.astype(np.float32))
    print("saved", E.shape)
