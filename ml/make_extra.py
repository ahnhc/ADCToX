"""Build per-prior extra feature files from the MONDO link (ml/link_mondo.py), for ml/lab.py --extra.
  extra_onto.npz   organ-system axes of the linked class's ancestors (13) + link similarity + linked flag
  extra_defs.npz   BioLORD embedding of the linked class's definition (zeros if none) + has-definition flag
  extra_both.npz   the two concatenated
Priors that did not link at THETA get zeros, i.e. the model is told nothing rather than something wrong."""
import pickle, numpy as np, torch, time
C = "/data/hyeongchanahn/adctox/ml_cache/"
L = pickle.load(open(C + "mondo_link.pkl", "rb")); df = L["df"].iloc[:1710]            # the 41 registry queries were appended after the FinnGen priors
onto = np.stack([np.r_[r.ax, r.sim * r.linked, float(r.linked)] for r in df.itertuples()]).astype(np.float32)
from sentence_transformers import SentenceTransformer
def enc():
    m = SentenceTransformer("FremyCompany/BioLORD-2023", device="cuda", model_kwargs={"torch_dtype": torch.float16})
    return m.encode([d if d else " " for d in df.defn], batch_size=64, normalize_embeddings=True, convert_to_numpy=True)
for _ in range(60):
    try: D = enc(); break
    except (torch.OutOfMemoryError, RuntimeError) as e:
        if not any(k in str(e) for k in ("CUBLAS", "out of memory", "CUDA error")): raise
        torch.cuda.empty_cache(); time.sleep(30)
has = (df.defn != "").values; D = np.where(has[:, None], D, 0).astype(np.float32); defs = np.c_[D, has.astype(np.float32)]
pn = np.array(df.prior_name, dtype=object)
for name, f in [("onto", onto), ("defs", defs), ("both", np.c_[onto, defs])]:
    np.savez(C + f"extra_{name}.npz", priors=pn, feat=f); print(name, f.shape)
