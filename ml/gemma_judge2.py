"""Second Gemma judge: one Gemma 4 E2B model (first 18 layers, LoRA) with four outputs read from the last prompt token.

    CUDA_VISIBLE_DEVICES=2 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache copy> python ml/gemma_judge2.py --tag v2

  organ  13 organ probabilities (as ml/gemma_judge.py), per-organ temperature and threshold
  valid  P(the text is a real input: a disease, symptom or history, not filler or gibberish)
  align  a 768-d vector in SapBERT's space: the text's disease, so any language links through the existing MONDO index
         (Korean text -> the vector of the English disease name)
  sym    which of the disease profiles (data/curated/disease_profiles) a symptom description points to

Training texts (gold concepts and their relatives are never targets of organ or align):
  ml/organ_head.texts + profile Korean names, everyday words and symptoms (as the first judge);
  HIRA KCD Korean names -> SapBERT vector of their English KCD name (a sample);
  Haiku 5.5 (data/curated/judge2/gen): ko_* Korean expressions of frequent concepts, sym_* patient-style symptom sentences
  for every profile, junk_* inputs that name nothing (valid = 0).
Held out: 10% of the concepts (organ calibration, align check), 10% of the junk (validity threshold).
Dev checks (never test): gold dev queries in English and Korean (data/curated/judge2/gen/koeval_*), symptom_eval_v0 dev half.
-> $ADCTOX_CACHE/gemma_judge2_<tag>/ (adapter_head.pt, calibration.npz, info.json), ml/results/benchmarks/gemma_judge2_<tag>.json
"""
import argparse, collections, glob, hashlib, json, os, random, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import torch
import adc_paths as P, eval_linking as EL, mondo_index as MI, linking_models as LM, organ_head as OH, suggest as SG, gemma_judge as GJ
from build_linking_pools import read_obo

AXES = MI.AXES; DEV = "cuda:0"; PROMPT = GJ.PROMPT; G2 = P.REPO + "data/curated/judge2/gen/"
HANGUL = lambda s: any("가" <= c <= "힣" for c in s)
JUNK_COPIES = 4                                                          # each training junk text this many times
SOURCES = ["mondo_names", "train_queries", "external", "profiles", "kcd", "gen_ko", "gen_sym", "mondo_ko", "ko2", "kotypo", "ko3"]     # junk always


def sym_split(t): return "dev" if int(hashlib.sha256(t.encode()).hexdigest(), 16) % 2 == 0 else "test"     # as ml/eval_symptoms.py


def jl(pattern):
    out = []
    for f in sorted(glob.glob(G2 + pattern)):
        for line in open(f, encoding="utf-8"):
            try: out.append(json.loads(line))
            except ValueError: pass
    return out


class Judge2(torch.nn.Module):
    def __init__(self, lm, hidden, n_sym):
        super().__init__(); self.lm = lm
        self.head = torch.nn.Linear(hidden, len(AXES)); self.valid = torch.nn.Linear(hidden, 1)
        self.align = torch.nn.Linear(hidden, 768); self.sym = torch.nn.Linear(hidden, n_sym)
        for m in (self.valid, self.sym): torch.nn.init.zeros_(m.weight); torch.nn.init.zeros_(m.bias)     # start at chance, not at a large loss
    def forward(self, ids, mask):
        h = self.lm(input_ids=ids, attention_mask=mask).last_hidden_state
        h = h[torch.arange(len(h)), mask.sum(1) - 1].float()
        return self.head(h), self.valid(h)[:, 0], torch.nn.functional.normalize(self.align(h), dim=-1), self.sym(h)


def predict(model, tok, texts, bs=128):
    model.eval(); out = [[], [], [], []]
    if not texts: return [np.zeros((0, 13)), np.zeros(0), np.zeros((0, 768)), np.zeros((0, 1))]
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            enc = tok([PROMPT.format(t) for t in texts[i:i + bs]], return_tensors="pt", padding=True, truncation=True, max_length=64)
            for k, z in enumerate(model(enc["input_ids"].to(DEV), enc["attention_mask"].to(DEV))): out[k].append(z.float().cpu().numpy())
    return [np.concatenate(o) for o in out]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--layers", type=int, default=18); ap.add_argument("--tag", default="v2")
    ap.add_argument("--rank", type=int, default=16); ap.add_argument("--epochs", type=int, default=2); ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--kcd", type=int, default=20000); ap.add_argument("--smoke", action="store_true"); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--stage", default="unstaged"); ap.add_argument("--note", default=""); ap.add_argument("--compare-to", default=None)
    ap.add_argument("--consist", type=float, default=0.0, help="weight of the Korean-English consistency loss (0: off)")
    ap.add_argument("--drop", default="", help="comma list of training sources to leave out (ablation): " + ",".join(SOURCES))
    a = ap.parse_args(); rng = random.Random(a.seed); torch.manual_seed(a.seed)
    import tuning_ledger as TL
    TL.write_card(a.tag, dict(tag=a.tag, stage=a.stage, note=a.note, compare_to=a.compare_to, started=time.strftime("%Y-%m-%d %H:%M"), args=vars(a),
                              git=TL.git_state(), data=TL.manifest(cache=P.CACHE), backbone=dict(model=GJ.GEMMA, revision=GJ.REV, prompt=PROMPT)))
    from peft import LoraConfig, get_peft_model
    T = read_obo(); held = LM.gold_held(T); labels, _ = LM.load_organ_labels()
    prof = SG.profiles(); pid = {p["id"]: k for k, p in enumerate(prof)}
    # ---- targets in SapBERT space: the vector of each concept's MONDO name (the index row the linker would find)
    MI.link(["x"]); Z = MI._IDX; ids = Z["_ids"]; names = [str(n) for n in Z["names"]]; row = {}
    for k, (t, n) in enumerate(zip(ids, names)):
        if t not in row or (t in T and n == T[t]["name"]): row[t] = k
    E = Z["E"].astype(np.float32)
    def cvec(t): return E[row[t]] if t in row else None
    # ---- items: (text, concept or None, organ vector or None, valid, align vector or None, sym class or -1)
    items = []; drop = {x for x in a.drop.split(",") if x}; unknown = drop - set(SOURCES)
    if unknown: raise SystemExit(f"unknown sources {sorted(unknown)}; known: {SOURCES}")
    def add(text, t=None, org=True, valid=1.0, vec=None, sym=True, alg=True, src="?"):
        if not text or not str(text).strip(): return
        ok = t is not None and t not in held
        o = np.array([x in labels[t] for x in AXES], np.float32) if (org and ok and t in labels) else None
        v = vec if vec is not None else (cvec(t) if (alg and ok) else None)
        items.append((str(text).strip(), t, o, valid, v, pid.get(t, -1) if (sym and t is not None) else -1, src))
    if "mondo_names" not in drop:                                             # MONDO names and synonyms (as organ_head.texts)
        for t in labels:
            if t not in held and t in T:
                for q in [T[t]["name"]] + T[t]["syn"][:5]: add(q, t, src="mondo_names")
    if "train_queries" not in drop:
        for f in sorted(glob.glob(P.REPO + "data/curated/train_queries/review/review2_*.jsonl")):
            for x in map(json.loads, open(f)):
                if x.get("validity") == "valid" and x.get("match") is True and x["concept"] in labels and x["concept"] not in held: add(x["query"], x["concept"], src="train_queries")
    ext = P.REPO + "data/curated/external/mentions_mondo.jsonl"                  # licensed corpus mentions, not in the repository
    if "external" not in drop and os.path.exists(ext):
        for r in map(json.loads, open(ext)):
            if r["split"] == "train" and len(r["mondo"]) == 1 and r["mondo"][0] in labels and r["mondo"][0] not in held: add(r["mention"], r["mondo"][0], src="external")
    elif "external" not in drop: drop.add("external"); print("external mentions not found: trained without them", flush=True)
    if "profiles" not in drop:
        for p in prof:
            for k in p.get("ko", []) + p.get("ko_lay", []): add(k, p["id"], src="profiles")
            for k in p.get("en", []) + p.get("abbr", []): add(k, p["id"], src="profiles")
            for k in p.get("symptoms_ko", [])[:3] + p.get("symptoms_en", [])[:3]: add(k, p["id"], alg=False, sym=False, src="profiles")
    n_kcd = 0
    if "kcd" not in drop:
        kcd = list(zip([str(x) for x in Z["ko_keys"]], [str(x) for x in Z["ko_vals"]])); rng.shuffle(kcd); kcd = kcd[: a.kcd]
        kv = MI._embed([v for _, v in kcd], DEV).astype(np.float32)
        top = np.concatenate([(torch.from_numpy(kv[i:i + 4096]).to(DEV) @ torch.from_numpy(E).to(DEV).T).argmax(1).cpu().numpy() for i in range(0, len(kv), 4096)])
        for (k, v), vec, j in zip(kcd, kv, top):
            if ids[j] in held: continue
            add(k, None, vec=vec, src="kcd"); n_kcd += 1
    gko = jl("ko_*.jsonl") if "gen_ko" not in drop else []; gsym = jl("sym_*.jsonl") if "gen_sym" not in drop else []; junk = jl("junk_*.jsonl")
    for x in gko:
        if x.get("id") in T: add(x.get("text"), x["id"], src="gen_ko")
    for x in gsym:
        if x.get("id") in pid: add(x.get("text"), x["id"], src="gen_sym")
    n_mk = 0
    if "mondo_ko" not in drop:                                                # reviewed Korean MONDO names (korean/mondo_ko.jsonl)
        for x in map(json.loads, open(P.REPO + "data/curated/korean/mondo_ko.jsonl", encoding="utf-8")):
            if x["conf"] == "low" or x["id"] not in T: continue
            for k in [x["ko"]] + x["alt"]: add(k, x["id"], src="mondo_ko"); n_mk += 1
    gko2 = jl("ko2_*.jsonl") if "ko2" not in drop else []
    for x in gko2:
        if x.get("id") in T: add(x.get("text"), x["id"], src="ko2")
    gtypo = jl("kotypo_*.jsonl") if "kotypo" not in drop else []             # rule-based Korean typos (ml/ko_typos.py)
    for x in gtypo:
        if x.get("id") in T: add(x.get("text"), x["id"], src="kotypo")
    gko3 = jl("ko3_*.jsonl") if "ko3" not in drop else []                    # short words, abbreviations, Korean-English mixes (ml/ko3_batches.py)
    for x in gko3:
        if x.get("id") in T: add(x.get("text"), x["id"], src="ko3")
    junk = list(dict.fromkeys(str(x.get("text", "")).strip() for x in junk if str(x.get("text", "")).strip())); rng.shuffle(junk)
    junk_val = junk[: len(junk) // 10]; junk_tr = junk[len(junk) // 10:]
    for j in junk_tr: items.append((j, None, None, 0.0, None, -1, "junk"))
    items = list({(x[0], x[1], x[3]): x for x in items}.values())
    items, n_leak = TL.drop_leaks(items)                                     # evaluation queries with their gold concept
    items += [x for x in items if x[6] == "junk"] * (JUNK_COPIES - 1)        # oversampled after the dedupe (before 2026-10-18 the dedupe undid it)
    concepts = sorted({x[1] for x in items if x[1] is not None}); rng.shuffle(concepts); val_c = set(concepts[: len(concepts) // 10])
    train = [x for x in items if x[1] is None or x[1] not in val_c]; val = [x for x in items if x[1] is not None and x[1] in val_c]
    if a.smoke: train, val = train[::300], val[::100]
    print(f"items {len(items)} (korean {sum(HANGUL(x[0]) for x in items)}, kcd {n_kcd}, gen ko {len(gko)}, gen sym {len(gsym)}, junk {len(junk)}), train {len(train)}, val {len(val)}", flush=True)
    outs = lambda x: [o for o, ok in (("organ", x[2] is not None), ("align", x[4] is not None), ("valid", True), ("sym", x[5] >= 0)) if ok]
    chk, bad = TL.checks(items, outs)
    TL.write_card(a.tag, dict(checks=chk, items=dict(total=len(items), train=len(train), val=len(val), korean=sum(HANGUL(x[0]) for x in items), kcd=n_kcd,
                  gen_ko=len(gko), gen_sym=len(gsym), junk=len(junk), junk_copies=JUNK_COPIES, mondo_ko=n_mk, ko2=len(gko2), kotypo=len(gtypo), ko3=len(gko3), dropped_eval_text=n_leak,
                  sources_left_out=sorted(drop), by_source=dict(collections.Counter(x[6] for x in train)), **{f"out_{o}": sum(o in outs(x) for x in train) for o in ("organ", "align", "valid", "sym")})))
    if bad: raise SystemExit("pre-training checks failed: " + "; ".join(bad))
    # ---- dev sets (computed before Gemma takes the GPU)
    Q = json.load(open(EL.D + "raw/queries_v0.json")); Gd = {x["qid"]: x for x in map(json.loads, open(EL.D + "gold_v0.jsonl"))}
    gold = [dict(Gd[q["qid"]], category=q["category"]) for q in Q]; groups = [q["group"] or q["qid"] for q in Q]
    dev = [i for i, g in enumerate(groups) if EL.split_of(g) == "dev"]
    ko = {x["qid"]: x["query_ko"] for x in jl("koeval_*.jsonl") if x.get("query_ko")}; Qko = [ko.get(q["qid"], q["query"]) for q in Q]
    links = MI.link([q["query"] for q in Q])
    links_ko = MI.link([(MI.korean(t) or t) for t in Qko])                                             # the app today: KCD name -> SapBERT
    SE = [json.loads(l) for l in open(P.REPO + "data/curated/disease_profiles/symptom_eval_v0.jsonl", encoding="utf-8") if l.strip()]
    SE = [s for s in SE if s["target"] in pid and sym_split(s["target"]) == "dev"]
    MI.close(); torch.cuda.empty_cache()
    tok, lm, path = GJ.load_backbone(a.layers); tok.padding_side = "right"
    lm = get_peft_model(lm, LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    model = Judge2(lm, lm.config.hidden_size, len(prof)).to(DEV)
    params = [p for p in model.parameters() if p.requires_grad]; print("trainable", sum(p.numel() for p in params), flush=True)
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0); bce = torch.nn.BCEWithLogitsLoss(reduction="none")
    BS = 32; steps = a.epochs * (len(train) // BS + 1); sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=steps, pct_start=0.05)
    def losses(b, out):
        zo, zv, va, zs = out; L = {}
        m = torch.tensor([x[2] is not None for x in b], device=DEV)
        if m.any():
            yo = torch.from_numpy(np.stack([x[2] if x[2] is not None else np.zeros(13, np.float32) for x in b])).to(DEV)
            L["organ"] = bce(zo, yo).mean(1)[m].mean()
        L["valid"] = bce(zv, torch.tensor([x[3] for x in b], device=DEV)).mean()
        m = [k for k, x in enumerate(b) if x[4] is not None]
        if m:
            tv = torch.nn.functional.normalize(torch.from_numpy(np.stack([b[k][4] for k in m])).to(DEV).float(), dim=-1); pv = va[m]
            sim = pv @ tv.T / 0.05; same = (tv @ tv.T) > 0.999; sim = sim.masked_fill(same & ~torch.eye(len(m), dtype=torch.bool, device=DEV), -1e4)
            L["align"] = torch.nn.functional.cross_entropy(sim, torch.arange(len(m), device=DEV)) + (1 - (pv * tv).sum(1)).mean()
        m = [k for k, x in enumerate(b) if x[5] >= 0]
        if m: L["sym"] = torch.nn.functional.cross_entropy(zs[m], torch.tensor([b[k][5] for k in m], device=DEV))
        return L
    # ---- Korean-English pairs (--consist): every Korean training text of a concept with the concept's English MONDO name. The
    # Korean text is pushed to give the outputs the English name gives (organ probabilities and align vector, English side fixed),
    # so what tuning teaches on English names carries over to Korean ones the training never saw. Train concepts only.
    pairs = [(x[0], T[x[1]]["name"]) for x in train if a.consist > 0 and x[1] is not None and x[1] in T and HANGUL(x[0])]
    PB = 16
    def consist_loss():
        q = [pairs[rng.randrange(len(pairs))] for _ in range(PB)]
        ek = tok([PROMPT.format(k) for k, _ in q], return_tensors="pt", padding=True, truncation=True, max_length=64)
        ee = tok([PROMPT.format(e) for _, e in q], return_tensors="pt", padding=True, truncation=True, max_length=64)
        zk, _, vk, _ = model(ek["input_ids"].to(DEV), ek["attention_mask"].to(DEV))
        with torch.no_grad(): ze, _, ve, _ = model(ee["input_ids"].to(DEV), ee["attention_mask"].to(DEV))
        return bce(zk, torch.sigmoid(ze)).mean() + (1 - (vk * ve).sum(1)).mean()
    best = (1e9, None); t0 = time.time()
    for ep in range(a.epochs):
        model.train(); idx = list(range(len(train))); rng.shuffle(idx)
        for s in range(0, len(idx), BS):
            b = [train[j] for j in idx[s:s + BS]]
            enc = tok([PROMPT.format(x[0]) for x in b], return_tensors="pt", padding=True, truncation=True, max_length=64)
            L = losses(b, model(enc["input_ids"].to(DEV), enc["attention_mask"].to(DEV)))
            if pairs: L["consist"] = a.consist * consist_loss()
            loss = sum(L.values())
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            if (s // BS) % 500 == 0: print(f"ep {ep} step {s // BS} " + " ".join(f"{k} {v.item():.3f}" for k, v in L.items()) + f" {time.time() - t0:.0f}s", flush=True)
        zo, zv, va, zs = predict(model, tok, [x[0] for x in val])
        yo = np.stack([x[2] if x[2] is not None else np.zeros(13) for x in val]); mo = np.array([x[2] is not None for x in val])
        vl = float(bce(torch.from_numpy(zo[mo]), torch.from_numpy(yo[mo]).float()).mean())
        print(f"epoch {ep} val organ loss {vl:.4f}", flush=True)
        TL.write_card(a.tag, dict(epochs=[*json.load(open(TL.CARDS + f"{a.tag}.json")).get("epochs", [])[:ep], dict(epoch=ep + 1, val_organ_loss=round(vl, 4), minutes=round((time.time() - t0) / 60, 1))]))
        if vl < best[0]: best = (vl, ep, {k: v.detach().cpu().clone() for k, v in model.state_dict().items() if "lora" in k or not k.startswith("lm.")})
    model.load_state_dict(best[2], strict=False)
    out = P.CACHE + f"gemma_judge2_{a.tag}/"; os.makedirs(out, exist_ok=True); torch.save(best[2], out + "adapter_head.pt")
    # ---- calibration on the held-out concepts and junk
    zo, zv, va, zs = predict(model, tok, [x[0] for x in val]); mo = np.array([x[2] is not None for x in val]); yo = np.stack([x[2] for x in val if x[2] is not None])
    zo = zo[mo]; lf = lambda z, y: float(bce(torch.from_numpy(z), torch.from_numpy(y).float()).mean()); temp, thr = [], []
    for k in range(13):
        tz = min(np.arange(0.5, 3.01, 0.1), key=lambda s_: lf(zo[:, k] / s_, yo[:, k])); p = 1 / (1 + np.exp(-zo[:, k] / tz)); y = yo[:, k] > 0
        tb = max(np.arange(0.2, 0.81, 0.05), key=lambda t_: 2 * ((p >= t_) & y).sum() / max(1, (p >= t_).sum() + y.sum())); temp.append(float(tz)); thr.append(float(tb))
    temp, thr = np.array(temp, np.float32), np.array(thr, np.float32)
    _, zj, _, _ = predict(model, tok, junk_val); pr = 1 / (1 + np.exp(-np.concatenate([zv, zj]))); yl = np.r_[np.ones(len(zv)), np.zeros(len(zj))]
    grid = list(np.arange(0.05, 0.96, 0.05)) + [0.97, 0.98, 0.99, 0.995]
    vthr = float(min((t_ for t_ in grid if (pr[yl == 0] >= t_).mean() == 0), default=0.995))     # lowest threshold that rejects every held-out junk text
    valid_info = dict(threshold=vthr, real_accepted=float((pr[yl == 1] >= vthr).mean()), junk_accepted=float((pr[yl == 0] >= vthr).mean()))
    ma = [k for k, x in enumerate(val) if x[4] is not None and x[1] in row]
    va_top = (torch.from_numpy(va[ma]).to(DEV) @ torch.from_numpy(E).to(DEV).T).argmax(1).cpu().numpy()
    align_val = dict(n=len(ma), top1=float(np.mean([ids[j] == val[k][1] for j, k in zip(va_top, ma)])),
                     top1_korean=float(np.mean([ids[j] == val[k][1] for j, k in zip(va_top, ma) if HANGUL(val[k][0])] or [np.nan])))
    # ---- gold dev, English and Korean: organs from the judge, the linker, or the aligned vector
    Et = torch.from_numpy(E).to(DEV)
    def dev_eval(texts, lk_rows):
        zo_, zv_, va_, _ = predict(model, tok, texts); J = 1 / (1 + np.exp(-zo_ / temp)) >= thr; V = 1 / (1 + np.exp(-zv_)) >= vthr
        s, j = (torch.from_numpy(va_).to(DEV) @ Et.T).max(1); s, j = s.cpu().numpy(), j.cpu().numpy()
        res = {}
        for theta in (None, 0.6, 0.7, 0.8):
            for gate in ("linker", "valid", "both"):
                pred = []
                for i, (lk, jj, vv) in enumerate(zip(lk_rows, J, V)):
                    ok = {"linker": lk.get("gate") is not False, "valid": bool(vv), "both": lk.get("gate") is not False and bool(vv)}[gate]
                    jo = [AXES[k] for k in np.where(jj)[0]] if ok else []
                    if theta is None: c, lo = (lk["mondo"] if lk["axes"] else None), lk["axes"]
                    else:
                        c = ids[j[i]] if s[i] >= theta and ok else None; lo = MI.concept(c)[1] if c else []
                        if not lo and lk["axes"]: c, lo = lk["mondo"], lk["axes"]
                    pred.append((c, lo or jo))
                m = EL.metrics(pred, gold, dev); res[f"{'linker' if theta is None else f'align{theta}'}+{gate}"] = {k: m[k] for k in ("macro_f1", "concept_acc", "false_accept_invalid", "coverage")}
        base = [((lk["mondo"] if lk["axes"] else None), lk["axes"] or (lk.get("judged", []) if lk.get("gate") is not False else [])) for lk in lk_rows]
        m = EL.metrics(base, gold, dev); res["app_0.3.8_rule_head"] = {k: m[k] for k in ("macro_f1", "concept_acc", "false_accept_invalid", "coverage")}
        return res
    MI.link(["x"])
    ev_en = dev_eval([q["query"] for q in Q], links); ev_ko = dev_eval(Qko, links_ko)
    # ---- symptom search, dev half: the sym head, and the aligned vector against the profile diseases
    _, _, va_s, zs_s = predict(model, tok, [s["query"] for s in SE]); pv = np.stack([cvec(p["id"]) if cvec(p["id"]) is not None else np.zeros(768, np.float32) for p in prof])
    def topk(scores):
        r = []
        for s, sc in zip(SE, scores):
            order = np.argsort(-sc)[:5]; ok = {s["target"], *s.get("also_ok", [])}
            r.append(next((i + 1 for i, o in enumerate(order) if prof[o]["id"] in ok), None))
        return {f"top{k}": round(float(np.mean([x is not None and x <= k for x in r])), 3) for k in (1, 3, 5)} | dict(n=len(r))
    zsm = zs_s - zs_s.max(1, keepdims=True); ps = np.exp(zsm) / np.exp(zsm).sum(1, keepdims=True)
    sym_ev = dict(sym_head=topk(ps), align=topk(va_s @ pv.T), mix=topk(ps + 0.5 * np.exp((va_s @ pv.T) / 0.05) / np.exp((va_s @ pv.T) / 0.05).sum(1, keepdims=True)))
    res = dict(tag=a.tag, layers=a.layers, rank=a.rank, epochs_best=best[1] + 1, n_train=len(train), n_items=len(items), valid=valid_info, align_val=align_val,
               gold_dev_en=ev_en, gold_dev_ko=ev_ko, n_ko_queries=len(ko), symptom_dev=sym_ev, minutes=round((time.time() - t0) / 60, 1))
    print(json.dumps(res, indent=1, ensure_ascii=False))
    np.savez(out + "calibration.npz", temp=temp, thr=thr, vthr=np.float32(vthr)); json.dump(dict(res, backbone=GJ.GEMMA, revision=GJ.REV, prompt=PROMPT, profiles=[p["id"] for p in prof]), open(out + "info.json", "w"), indent=1, ensure_ascii=False)
    json.dump(res, open(P.REPO + f"ml/results/benchmarks/gemma_judge2_{a.tag}.json", "w"), indent=1, ensure_ascii=False)
    pick = lambda ev, k: round(ev[k]["macro_f1"], 3)
    TL.write_card(a.tag, dict(finished=time.strftime("%Y-%m-%d %H:%M"), chosen_epoch=best[1] + 1, calibration=dict(temp=[round(float(x), 2) for x in temp], thr=[round(float(x), 2) for x in thr], valid=valid_info),
                  results=dict(en_pipeline=pick(ev_en, "linker+valid"), en_single=pick(ev_en, "align0.7+valid"), ko_pipeline=pick(ev_ko, "linker+valid"), ko_single=pick(ev_ko, "align0.7+valid"),
                               align_top1=round(align_val["top1"], 3), sym_top3=sym_ev["mix"]["top3"], valid_threshold=vthr)))
    TL.render()


if __name__ == "__main__":
    main()
