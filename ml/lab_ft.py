"""End-to-end LoRA fine-tuning of the text encoder, evaluated exactly like ml/lab.py.

Protocol, fixed before the first run:
  * every fold fine-tunes a FRESH copy of the pretrained encoder on that fold's training diseases only, so
    a held-out disease name is never seen by the encoder (fine-tuning once on everything and evaluating
    afterwards would leak);
  * one hyper-parameter set (LoRA r=8, alpha=16, dropout 0.1 on q,v; encoder lr 1e-4, head lr 2e-3,
    8 warm-up epochs with the encoder frozen); no sweep. If it does not help, that is the result;
  * the same folds, baselines (lookup, frozen-embedding kNN) and family-bootstrapped metrics as lab.py.
Each step encodes a chunk of 128 training diseases with gradients. The 193 outcome names use the frozen
pretrained embedding (no LoRA on that side): the GPUs this runs on are shared and almost full, and the outcome
side is learned through free per-outcome vectors anyway. Decided before any result existed.
"""
import argparse, json, os, pickle, time, sys, warnings
import numpy as np, pandas as pd, torch, torch.nn as nn
from scipy.stats import spearmanr
from transformers import AutoTokenizer, AutoModel
from peft import LoraConfig, get_peft_model
sys.path.insert(0, "/home/hyeongchanahn/CONI/adctox/ml")
import lab
warnings.filterwarnings("ignore")
MODEL = {"biolord": "FremyCompany/BioLORD-2023", "sapbert": "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"}
DEV = "cuda:0"; MAXLEN = 48; CHUNK = 128; WARM = 8; MAXEP = 60; PATIENCE = 12; LR_ENC = 1e-4; LR_HEAD = 2e-3

def pool(h, mask, kind):
    if kind == "cls": return h[:, 0]
    m = mask.unsqueeze(-1).to(h.dtype); return (h * m).sum(1) / m.sum(1)

class Enc(nn.Module):
    def __init__(s, name, kind):
        super().__init__(); s.kind = kind; base = AutoModel.from_pretrained(name)
        cfg = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.1, target_modules=["q", "v"] if "biolord" in name.lower() else ["query", "value"])
        s.m = get_peft_model(base, cfg)
    def forward(s, ids, mask):
        with torch.autocast("cuda", dtype=torch.bfloat16):
            h = s.m(input_ids=ids, attention_mask=mask).last_hidden_state
        e = pool(h.float(), mask, s.kind); return e / (e.norm(dim=1, keepdim=True) + 1e-9)

import subprocess
def pick_device(min_gb=2.0):
    free = [int(x) for x in subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.split()]
    vis = [int(v) for v in os.environ.get("CUDA_VISIBLE_DEVICES", ",".join(map(str, range(len(free))))).split(",")]
    best = max(vis, key=lambda i: free[i])
    if free[best] < min_gb * 1024: raise torch.OutOfMemoryError(f"no GPU has {min_gb} GB free (best {free[best]} MiB)")
    return f"cuda:{vis.index(best)}"

@lab.retry_oom
def fit_fold(args, tok_p, tok_o, Xp, y, w, rows, nl, nd, n_out, tr, va, te, seed, weighted, Oarr):
    global DEV
    DEV = pick_device(); tok_p = tuple(t.to(DEV) for t in tok_p); Ot = torch.tensor(Oarr, device=DEV)
    torch.manual_seed(seed); np.random.seed(seed); name = MODEL[args.emb]; kind = "mean" if args.emb == "biolord" else "cls"
    enc = Enc(name, kind).to(DEV); dP = 768 + (Xp.shape[1] if Xp is not None else 0)
    net = (lab.TwoTower(dP, 768, nl + nd) if args.arch == "twotower" else lab.Bilinear(dP, 768, n_out, nl)).to(DEV)
    lora = [p for p in enc.parameters() if p.requires_grad]
    opt = torch.optim.AdamW([{"params": lora, "lr": LR_ENC, "weight_decay": 0.0}, {"params": net.parameters(), "lr": LR_HEAD, "weight_decay": 1e-2}])
    mu, sd = y[tr].mean(), y[tr].std(); yt = torch.tensor((y - mu) / sd, device=DEV, dtype=torch.float32); wt = torch.tensor(w, device=DEV, dtype=torch.float32)
    ri = {k: torch.tensor(v, device=DEV) for k, v in rows.items()}; eye = torch.eye(nl + nd, device=DEV)
    Xt = torch.tensor(Xp, device=DEV) if Xp is not None else None
    ctx_of = lambda ix: torch.cat([eye[ri["li"][ix]], eye[nl + ri["di"][ix]]], 1)[:, :nl + nd]

    def encode(tok, idx, grad):
        out = []
        with torch.set_grad_enabled(grad):
            for i in range(0, len(idx), 512):
                j = idx[i:i + 512]; out.append(enc(tok[0][j], tok[1][j]))
        return torch.cat(out)
    def run_rows(prior_ids, row_ix, grad):
        """forward the given rows; prior_ids = the distinct priors those rows belong to."""
        Pe = encode(tok_p, prior_ids, grad); Oe = Ot
        if Xt is not None: Pe = torch.cat([Pe, Xt[prior_ids]], 1)
        loc = torch.full((tok_p[0].shape[0],), -1, device=DEV, dtype=torch.long); loc[prior_ids] = torch.arange(len(prior_ids), device=DEV)
        return net(Pe[loc[ri["pi"][row_ix]]], Oe[ri["oi"][row_ix]], ri["oi"][row_ix], ri["li"][row_ix], ctx_of(row_ix))
    def predict(rows_np):
        enc.eval(); net.eval(); ix = torch.tensor(rows_np, device=DEV); pr = torch.unique(ri["pi"][ix])
        with torch.no_grad(): return run_rows(pr, ix, False)

    tr_t = torch.tensor(tr, device=DEV); tr_pri = torch.unique(ri["pi"][tr_t]); best, bad, state = 1e9, 0, None
    for ep in range(MAXEP):
        enc.train(); net.train(); perm = tr_pri[torch.randperm(len(tr_pri), device=DEV)]; train_enc = ep >= WARM
        for i in range(0, len(perm), CHUNK):
            ch = perm[i:i + CHUNK]; isin = torch.zeros(tok_p[0].shape[0], dtype=torch.bool, device=DEV); isin[ch] = True
            rix = tr_t[isin[ri["pi"][tr_t]]]
            pred = run_rows(ch, rix, train_enc); l = nn.functional.huber_loss(pred, yt[rix], reduction="none")
            l = (l * wt[rix]).mean() if weighted else l.mean(); opt.zero_grad(); l.backward(); opt.step()
        v = nn.functional.mse_loss(predict(va), yt[torch.tensor(va, device=DEV)]).item()
        if v < best - 1e-4: best, bad = v, 0; state = ({k: x.detach().clone() for k, x in enc.state_dict().items() if "lora" in k}, {k: x.clone() for k, x in net.state_dict().items()})
        else:
            bad += 1
            if bad >= PATIENCE and ep >= WARM + 2: break
    enc.load_state_dict(state[0], strict=False); net.load_state_dict(state[1])
    return predict(te).cpu().numpy() * sd + mu

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True); ap.add_argument("--emb", default="biolord", choices=list(MODEL)); ap.add_argument("--arch", default="twotower")
    ap.add_argument("--weighted", type=int, default=0); ap.add_argument("--extra", default=None)
    ap.add_argument("--regimes", default="cluster"); ap.add_argument("--seeds", default="0,1,2")
    a = ap.parse_args(); seeds = [int(s) for s in a.seeds.split(",")]
    m = lab.load_rows(); P, O, rows, nl, nd, up = lab.table(m, a.emb, a.extra); y = m.y.values.astype(np.float32); w = m.w.values.astype(np.float32)
    Pn = P[:, :O.shape[1]]; Pn = Pn / np.linalg.norm(Pn, axis=1, keepdims=True); SIM = Pn @ Pn.T
    Xp = P[:, 768:].astype(np.float32) if a.extra else None
    tok = AutoTokenizer.from_pretrained(MODEL[a.emb]); uo = m.drop_duplicates("outcome_name").reset_index(drop=True)
    T = lambda strs: tuple(torch.tensor(v) for v in (lambda e: (e["input_ids"].numpy(), e["attention_mask"].numpy()))(tok([s.strip() for s in strs], padding="max_length", truncation=True, max_length=MAXLEN, return_tensors="pt")))
    tok_p = T(list(up.prior_longname.fillna(up.prior_name))); tok_o = T(list(uo.outcome_longname))
    out = dict(config=vars(a), regimes={}); per_prior = {}
    for regime in a.regimes.split(","):
        acc = {k: [] for k in ["lookup", "knn", "model"]}; rho_acc = {k: {} for k in acc}
        for seed in seeds:
            f, key = lab.splits(m, regime, seed); pred = {k: np.zeros(len(m)) for k in acc}
            for k in range(lab.FOLDS):
                te = np.where(f == k)[0]; trall = np.where(f != k)[0]; mask = np.zeros(len(m), bool); mask[trall] = True
                kk = key.iloc[trall].unique(); r = np.random.default_rng(100 + seed * 10 + k); vk = set(r.choice(kk, max(1, len(kk) // 10), replace=False))
                isv = key.iloc[trall].isin(vk).values; va, tr = trall[isv], trall[~isv]; t0 = time.time()
                pred["lookup"][te] = lab.lookup(m, trall, te); pred["knn"][te] = lab.knn_all(m, rows, SIM, y, mask)[te]
                pred["model"][te] = fit_fold(a, tok_p, tok_o, Xp, y, w, rows, nl, nd, O.shape[0], tr, va, te, seed, bool(a.weighted), O)
                print(f"   fold {k} done in {time.time() - t0:.0f}s", flush=True)
            for n_, v in pred.items():
                rho = lab.organ(m, v); [rho_acc[n_].setdefault(p, []).append(x) for p, x in rho.items()]
                acc[n_].append(dict(r2=1 - ((y - v) ** 2).sum() / ((y - y.mean()) ** 2).sum(), spearman=spearmanr(y, v)[0], organ=float(np.mean(list(rho.values())))))
            print(f"[{a.name}|{regime}] seed {seed}", {n_: round(acc[n_][-1]["r2"], 3) for n_ in acc}, flush=True)
        mean_rho = {n_: {p: float(np.mean(v)) for p, v in rho_acc[n_].items()} for n_ in acc}; per_prior[regime] = mean_rho
        out["regimes"][regime] = {n_: {k: float(np.mean([x[k] for x in L])) for k in ["r2", "spearman", "organ"]} for n_, L in acc.items()}
        for nm, (p, q) in dict(model_gain_over_lookup=("model", "lookup"), knn_gain_over_lookup=("knn", "lookup"), model_minus_knn=("model", "knn")).items():
            out["regimes"][regime][nm] = lab.fam_boot(m, mean_rho[p], mean_rho[q])
        g = out["regimes"][regime]; print(f"== {a.name} | {regime}: model R2 {g['model']['r2']:+.3f} (knn {g['knn']['r2']:+.3f}, lookup {g['lookup']['r2']:+.3f}) | gain over lookup "
              f"{g['model_gain_over_lookup']['delta']:+.3f} [{g['model_gain_over_lookup']['lo']:+.3f},{g['model_gain_over_lookup']['hi']:+.3f}]", flush=True)
    os.makedirs(lab.RES, exist_ok=True); json.dump(out, open(lab.RES + f"{a.name}.json", "w"), indent=1); pickle.dump(per_prior, open(lab.C + f"lab_{a.name}.pkl", "wb"))

if __name__ == "__main__":
    main()
