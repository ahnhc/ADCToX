"""Pretrain a well-known architecture from random weights on medical text, for the from-scratch judge (ml/scratch_judge.py).

    CUDA_VISIBLE_DEVICES=1 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<cache> python ml/scratch_pretrain.py --tag p1 --arch bert-medium --hours 40
    -> /data/hyeongchanahn/adctox/work/pretrain_<tag>/ (a Hugging Face model folder: config, weights, tokenizer, corpus manifest)
    then: python ml/scratch_judge.py --backbone /data/hyeongchanahn/adctox/work/pretrain_<tag> ...

Why: the judge trained from scratch on disease names alone (X0, X1, ml/docs/scratch_model.md) cannot judge diseases it never
saw, because it has no general medical knowledge; Gemma has it from pretraining. This gives the from-scratch model its own
pretraining: masked-language modelling (BERT's objective) over the medical text available here, so all its knowledge comes
from sources we chose and can list.

Architectures (random initial weights, nothing pretrained is loaded):
  bert-medium   BERT (Devlin et al. 2019), 8 layers, 512 wide, 8 heads, ~45M parameters with the tokenizer below
  bert-base     BERT, 12 layers, 768 wide, 12 heads, ~110M
  bert-large    BERT, 24 layers, 1024 wide, 16 heads, ~335M
  modernbert    ModernBERT (Warner et al. 2024), 16 layers, 512 wide, 8 heads (rotary positions, GeGLU, alternating attention)
Tokenizer: BPE, VOCAB symbols, NFD normalisation (Hangul as jamo, so Korean typos change one or two symbols), trained on the corpus.
Corpus (manifest written next to the model; one line = one text):
  umls_def     UMLS definitions (MRDEF) from sources of restriction level 0 (MeSH, NCI, MedlinePlus, CHV, HPO, OMIM, PDQ, ...)
  umls_names   for each UMLS concept with level-0 English or Korean names: "name ; synonym ; synonym ..."
  mondo        MONDO name, synonyms and definition per concept
  ko           Korean MONDO names, KCD Korean names with their English names, the Korean training expressions (judge2/gen)
  local        the project's downloaded medical documents: PMC XML, ClinicalTrials.gov JSON, DailyMed HTML, FDA labels
  pubmed       PubMed abstracts, when a folder of them is given (--pubmed)
  hpo          HPO term name, synonyms and definition per term (data/raw/hpo/hp.obo)
  hpo_dis      per disease concept: "name: phenotype (frequency) ; ..." from phenotype.hpoa (concept_organs/v5/input/concepts.jsonl)
--upsample N repeats the structured sources (umls_def, umls_names, mondo, hpo, hpo_dis) N times (p3: 10). --wwm masks whole words
(BERT whole-word masking; the tokenizer then marks word continuations with "##"). --bs is the batch per optimizer step; the
largest micro-batch that fits the GPU is found at start and gradients are accumulated up to --bs. A copy of the weights is kept
every --keep-every hours (ckpt_<h>h/). Several GPUs: torchrun --nproc_per_node N ml/scratch_pretrain.py ... (data parallel; each
GPU takes --bs/N of every batch; rank 0 writes the corpus and the weights; the lr schedule and the stop follow rank 0's clock).
Gold isolation: the structured entries (umls_def, umls_names, mondo) of gold concepts and their relatives are left out, as for
training; free text (local, pubmed) is not filtered, as no pretraining corpus can be. A line equal to an evaluation question is
dropped everywhere.
"""
import argparse, contextlib, glob, html, json, math, os, random, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import numpy as np, torch
import adc_paths as P

VOCAB, SEQ = 32000, 128
WORK = "/data/hyeongchanahn/adctox/work/"
META = "/data/hyeongchanahn/adctox/raw/umls/2026AA/META/"
ARCH = {"bert-medium": dict(kind="bert", num_hidden_layers=8, hidden_size=512, num_attention_heads=8, intermediate_size=2048),
        "bert-base": dict(kind="bert", num_hidden_layers=12, hidden_size=768, num_attention_heads=12, intermediate_size=3072),
        "bert-large": dict(kind="bert", num_hidden_layers=24, hidden_size=1024, num_attention_heads=16, intermediate_size=4096),
        "modernbert": dict(kind="modernbert", num_hidden_layers=16, hidden_size=512, num_attention_heads=8, intermediate_size=1536)}
TAG = re.compile(r"<[^>]+>"); WS = re.compile(r"\s+")


def clean(t): return WS.sub(" ", html.unescape(TAG.sub(" ", t))).strip()


def strings(x, out):
    if isinstance(x, str):
        if len(x) > 40 and " " in x: out.append(x)
    elif isinstance(x, dict): [strings(v, out) for v in x.values()]
    elif isinstance(x, list): [strings(v, out) for v in x]


def corpus(pubmed=None, meta=META):
    import linking_models as LM, tuning_ledger as TL, umls_build as UB
    from build_linking_pools import read_obo
    T = read_obo(); held = LM.gold_held(T); ev = TL.eval_concepts(); src = {}
    held_names = {TL.norm(n) for t in held if t in T for n in [T[t]["name"]] + T[t]["syn"]}
    # ---- UMLS (level-0 sources only)
    if os.path.exists(meta + "MRSAB.RRF"):
        sab0 = {f[3] for f in (l.split("|") for l in open(meta + "MRSAB.RRF", encoding="utf-8")) if f[13] == "0"}
        xref = UB.mondo_xrefs(os.path.join(P.REPO, "data/raw_big/mondo/2026-10-07/mondo.obo")); names = {}
        for l in open(meta + "MRCONSO.RRF", encoding="utf-8"):
            f = l.split("|")
            if f[11] in sab0 and f[1] in ("ENG", "KOR") and f[16] == "N" and len(f[14]) <= 120: names.setdefault(f[0], []).append(f[14])
        bad = {c for c, ns in names.items() if xref.get(c, set()) & held or any(TL.norm(n) in held_names for n in ns)}
        src["umls_names"] = [" ; ".join(list(dict.fromkeys(ns))[:12]) for c, ns in names.items() if c not in bad and len(ns) > 1]
        src["umls_def"] = [clean(f[5]) for f in (l.split("|") for l in open(meta + "MRDEF.RRF", encoding="utf-8")) if f[4] in sab0 and f[6] == "N" and f[0] not in bad]
    # ---- MONDO
    src["mondo"] = [" ; ".join([x["name"]] + x["syn"]) + (". " + x["defn"] if x["defn"] else "") for t, x in T.items() if t not in held and not x["name"].startswith("obsolete")]
    # ---- Korean
    ko = [f"{x['ko']} ; {' ; '.join(x['alt'])} ; {x['en']}" for x in map(json.loads, open(P.REPO + "data/curated/korean/mondo_ko.jsonl", encoding="utf-8")) if x["id"] not in held]
    Z = np.load(os.path.join(P.CACHE, "mondo_index.npz"), allow_pickle=True); ko += [f"{k} ; {v}" for k, v in zip(Z["ko_keys"], Z["ko_vals"])]
    for f in glob.glob(P.REPO + "data/curated/judge2/gen/*.jsonl"):
        if "koeval" in f: continue
        for l in open(f, encoding="utf-8"):
            try: x = json.loads(l)
            except ValueError: continue
            if x.get("id") not in held and x.get("text"): ko.append(x["text"])
    src["ko"] = ko
    # ---- local documents
    loc = []
    for f in glob.glob(P.REPO + "data/raw_big/pmc/**/*.xml", recursive=True) + glob.glob(P.REPO + "data/raw_big/dailymed/**/*.html", recursive=True):
        loc += [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", clean(open(f, encoding="utf-8", errors="ignore").read())) if len(s) > 40]
    for f in glob.glob(P.REPO + "data/raw_big/ctgov/**/*.json", recursive=True) + glob.glob(P.REPO + "data/raw_big/openfda_label/**/*.json", recursive=True) \
             + glob.glob(P.REPO + "data/raw_big/eligibility/**/*.json", recursive=True):
        try: strings(json.load(open(f, encoding="utf-8")), loc)
        except (ValueError, UnicodeDecodeError): pass
    src["local"] = [clean(s) for s in loc]
    if pubmed:
        pm = []
        for f in sorted(glob.glob(os.path.join(pubmed, "*.txt"))): pm += [l.strip() for l in open(f, encoding="utf-8") if len(l) > 40]
        src["pubmed"] = pm
    # ---- HPO terms and disease phenotype annotations (gold concepts and their relatives left out)
    hp, cur = [], None
    for l in open(P.REPO + "data/raw/hpo/hp.obo", encoding="utf-8"):
        l = l.rstrip("\n")
        if l == "[Term]": cur = dict(name="", syn=[], defn=""); hp.append(cur)
        elif l.startswith("[") : cur = None
        elif cur is not None and l.startswith("name: "): cur["name"] = l[6:]
        elif cur is not None and l.startswith("synonym: "): cur["syn"].append(l.split('"')[1])
        elif cur is not None and l.startswith("def: "): cur["defn"] = l.split('"')[1]
        elif cur is not None and l == "is_obsolete: true": cur["name"] = ""
    src["hpo"] = [" ; ".join([x["name"]] + x["syn"][:10]) + (". " + x["defn"] if x["defn"] else "") for x in hp if x["name"]]
    hd = []
    for x in map(json.loads, open(P.REPO + "data/curated/concept_organs/v5/input/concepts.jsonl", encoding="utf-8")):
        if x["id"] in held or not x.get("hpo_phenotypes"): continue
        ph = [h["name"] + (f" ({h['frequency']})" if h.get("frequency") else "") if isinstance(h, dict) else str(h) for h in x["hpo_phenotypes"]]
        hd.append(x["name"] + ": " + " ; ".join(ph))
    src["hpo_dis"] = hd
    for k in src: src[k] = [s for s in dict.fromkeys(src[k]) if s and TL.norm(s) not in ev]
    return src


def build(lines, out, wwm=False, tok_lines=None):
    import transformers as T
    from tokenizers import Tokenizer, models, trainers, pre_tokenizers, normalizers, processors
    tk = Tokenizer(models.BPE(unk_token="[UNK]", continuing_subword_prefix="##" if wwm else None)); tk.normalizer = normalizers.NFD()
    tk.pre_tokenizer = pre_tokenizers.Sequence([pre_tokenizers.Whitespace(), pre_tokenizers.Digits(individual_digits=True)])
    kw = dict(continuing_subword_prefix="##") if wwm else {}
    tk.train_from_iterator((tok_lines or lines)[:2_000_000], trainers.BpeTrainer(vocab_size=VOCAB, min_frequency=2, special_tokens=["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"], **kw))
    if wwm:
        from tokenizers import decoders
        tk.decoder = decoders.WordPiece(prefix="##")
    tk.post_processor = processors.TemplateProcessing(single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 2), ("[SEP]", 3)])
    fast = T.PreTrainedTokenizerFast(tokenizer_object=tk, unk_token="[UNK]", pad_token="[PAD]", cls_token="[CLS]", sep_token="[SEP]", mask_token="[MASK]")
    fast.save_pretrained(out)
    # ---- pack the corpus into SEQ-token blocks
    parts = []
    for i in range(0, len(lines), 20000):
        parts.append(np.fromiter((t for e in tk.encode_batch(lines[i:i + 20000], add_special_tokens=False) for t in e.ids + [3]), np.int32))
    del lines; ids = np.concatenate(parts); del parts
    blocks = ids[: len(ids) // (SEQ - 1) * (SEQ - 1)].reshape(-1, SEQ - 1)
    blocks = np.concatenate([np.full((len(blocks), 1), 2, np.int32), blocks], 1); del ids
    return tk, blocks


def _cont(b): return np.ascontiguousarray(b)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tag", required=True); ap.add_argument("--arch", default="bert-medium", choices=list(ARCH))
    ap.add_argument("--hours", type=float, default=40); ap.add_argument("--bs", type=int, default=128); ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--pubmed", default=None); ap.add_argument("--seed", type=int, default=7); ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--upsample", type=int, default=1); ap.add_argument("--wwm", action="store_true"); ap.add_argument("--keep-every", type=float, default=0)
    ap.add_argument("--warmup", type=int, default=2000)
    a = ap.parse_args(); random.seed(a.seed); torch.manual_seed(a.seed)
    import torch.distributed as dist
    world = int(os.environ.get("WORLD_SIZE", 1)); rank = int(os.environ.get("RANK", 0))
    if world > 1: torch.cuda.set_device(int(os.environ["LOCAL_RANK"])); dist.init_process_group("nccl")
    assert a.bs % world == 0, "--bs must divide by the number of GPUs"
    import transformers as T, tuning_ledger as TL
    from tokenizers import Tokenizer, models, trainers, pre_tokenizers, normalizers, processors
    out = WORK + f"pretrain_{a.tag}/"; os.makedirs(out, exist_ok=True); t0 = time.time()
    if world > 1 and rank > 0: dist.barrier()                                              # rank 0 builds (or finds) the corpus first
    cached = os.path.exists(out + "blocks.npy") and os.path.exists(out + "corpus.json") and not a.smoke     # a restart reuses the tokenized corpus
    if cached:
        man = json.load(open(out + "corpus.json")); blocks = np.load(out + "blocks.npy"); tk = Tokenizer.from_file(out + "tokenizer.json")
    else:
        src = corpus(a.pubmed); man = {k: dict(lines=len(v), chars=sum(map(len, v))) for k, v in src.items()}
        print(json.dumps(man, indent=1), flush=True)
        STRUCT = ("umls_def", "umls_names", "mondo", "hpo", "hpo_dis")
        man = {k: dict(v, repeats=a.upsample if k in STRUCT else 1) for k, v in man.items()}
        uniq = [s for v in src.values() for s in v]; random.shuffle(uniq)                       # the tokenizer learns from unique lines
        lines = [s for k, v in src.items() for s in v * (a.upsample if k in STRUCT else 1)]; random.shuffle(lines); del src
        if a.smoke: lines = lines[:20000]; uniq = uniq[:20000]
        tk, blocks = build(lines, out, wwm=a.wwm, tok_lines=uniq); del uniq
        np.save(out + "blocks.npy", blocks); json.dump(man, open(out + "corpus.json", "w"), indent=1)
    if world > 1 and rank == 0: dist.barrier()
    blocks = _cont(blocks)
    cfg = dict(ARCH[a.arch]); kind = cfg.pop("kind")
    if kind == "bert": conf = T.BertConfig(vocab_size=VOCAB, max_position_embeddings=512, pad_token_id=0, **cfg); model = T.BertForMaskedLM(conf)
    else: conf = T.ModernBertConfig(vocab_size=VOCAB, max_position_embeddings=512, pad_token_id=0, bos_token_id=2, eos_token_id=3, cls_token_id=2, sep_token_id=3, **cfg); model = T.ModernBertForMaskedLM(conf)
    model = model.cuda(); n_par = sum(p.numel() for p in model.parameters())
    info = dict(tag=a.tag, arch=a.arch, architecture=kind, config=cfg, parameters=n_par, init="random", vocab=VOCAB, seq=SEQ, tokens=int(blocks.size),
                blocks=len(blocks), corpus=man, git=TL.git_state(), started=time.strftime("%Y-%m-%d %H:%M"), upsample=a.upsample, batch=a.bs,
                objective="masked LM, 15% (80/10/10)" + (", whole-word masking" if a.wwm else ""))
    info.update(gpus=world)
    if rank == 0: json.dump(info, open(out + "pretrain_info.json", "w"), indent=1); print(json.dumps({k: v for k, v in info.items() if k != "corpus"}, indent=1), flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, betas=(0.9, 0.98), weight_decay=0.01)
    vocab = tk.get_vocab(); start = torch.ones(VOCAB, dtype=torch.bool, device="cuda")       # token starts a word (for --wwm)
    if a.wwm:
        for t, i in vocab.items():
            if t.startswith("##") and i < VOCAB: start[i] = False

    def masked(x):
        y = x.clone()
        if a.wwm:
            wid = torch.cumsum(start[x].long(), 1); m = torch.gather(torch.rand(x.shape[0], x.shape[1] + 1, device="cuda"), 1, wid) < 0.15
        else: m = torch.rand(x.shape, device="cuda") < 0.15
        m &= x > 4; y[~m] = -100; r = torch.rand(x.shape, device="cuda")
        x = torch.where(m & (r < 0.8), torch.full_like(x, 4), x); x = torch.where(m & (r >= 0.8) & (r < 0.9), torch.randint(5, VOCAB, x.shape, device="cuda"), x)
        return x, y

    def fits(n):                                                                          # largest micro-batch that runs
        try:
            x, y = masked(torch.from_numpy(blocks[:n].astype(np.int64)).cuda())
            with torch.autocast("cuda", dtype=torch.bfloat16): l = model(input_ids=x, labels=y).loss
            l.backward(); opt.zero_grad(set_to_none=True); torch.cuda.synchronize(); return True
        except torch.OutOfMemoryError: opt.zero_grad(set_to_none=True); torch.cuda.empty_cache(); return False
    per = a.bs // world                                                                   # this GPU's share of each batch
    micro = next((n for n in (1024, 768, 512, 384, 256, 192, 128, 96, 64, 32) if n <= per and per % n == 0 and fits(n)), 32)
    if world > 1:                                                                         # every GPU uses the smallest micro-batch any of them found
        mt = torch.tensor(micro, device="cuda"); dist.all_reduce(mt, op=dist.ReduceOp.MIN); micro = int(mt)
    core = model; model = torch.nn.parallel.DistributedDataParallel(model) if world > 1 else model
    micro = max(32, micro // 2) if micro < per else micro                                 # head-room for the other GPU user
    accum = per // micro; torch.cuda.empty_cache(); print(f"batch {a.bs} = micro {micro} x accumulation {accum}", flush=True)
    info.update(micro_batch=micro, accumulation=accum)
    if rank == 0: json.dump(info, open(out + "pretrain_info.json", "w"), indent=1)
    t0 = time.time(); budget = a.hours * 3600; step = 0; rng = np.random.default_rng(a.seed); last_save = last_keep = time.time(); losses = []
    nb = len(blocks) // a.bs
    def elapsed():                                                                        # rank 0's clock, so every GPU stops at the same step
        if world == 1: return time.time() - t0
        e = torch.tensor(time.time() - t0, device="cuda", dtype=torch.float64); dist.broadcast(e, 0); return float(e)
    el = 0.0
    while el < budget:
        for k in rng.permutation(nb):
            el = elapsed(); frac = min(1, el / budget)                                        # cosine over the time budget (a step-count estimate from the first steps ran out early: p3)
            lr = a.lr * min(1, (step + 1) / a.warmup) * 0.5 * (1 + math.cos(math.pi * frac))
            for g in opt.param_groups: g["lr"] = lr
            while True:                                                                       # out of memory (the GPU is shared): halve the micro-batch, redo the step
                try:
                    opt.zero_grad(set_to_none=True); tl = 0.0
                    for u in range(accum):
                        b0 = k * a.bs + rank * per + u * micro
                        x, y = masked(torch.from_numpy(blocks[b0:b0 + micro].astype(np.int64)).cuda())
                        sync = world == 1 or u == accum - 1
                        with (contextlib.nullcontext() if sync else model.no_sync()):
                            with torch.autocast("cuda", dtype=torch.bfloat16): loss = model(input_ids=x, labels=y).loss / accum
                            loss.backward()
                        tl += loss.item()
                    break
                except torch.OutOfMemoryError:
                    if micro <= 8 or world > 1: raise                                        # with several GPUs a retry on one alone would hang the others
                    opt.zero_grad(set_to_none=True); x = y = loss = None; torch.cuda.empty_cache(); micro //= 2; accum *= 2
                    print(f"out of memory: micro-batch {micro} x accumulation {accum}", flush=True)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); step += 1; losses.append(tl)
            if step % 200 == 0 and rank == 0: print(f"step {step} loss {np.mean(losses[-200:]):.3f} lr {lr:.2e} {(time.time() - t0) / 3600:.2f}h", flush=True)
            done = el >= budget or (a.smoke and step >= 100)
            if rank == 0 and (time.time() - last_save > 3600 or done):
                core.save_pretrained(out); last_save = time.time()
                json.dump(dict(info, steps=step, hours=round((time.time() - t0) / 3600, 2), loss=float(np.mean(losses[-200:]))), open(out + "pretrain_info.json", "w"), indent=1)
            if rank == 0 and a.keep_every and time.time() - last_keep > a.keep_every * 3600:
                kd = out + f"ckpt_{(time.time() - t0) / 3600:.0f}h/"; core.save_pretrained(kd); last_keep = time.time()
                json.dump(dict(steps=step, loss=float(np.mean(losses[-200:]))), open(kd + "state.json", "w"))
            if done: break
        if a.smoke: break
    if rank == 0: core.save_pretrained(out); print("->", out, flush=True)
    if world > 1: dist.destroy_process_group()


if __name__ == "__main__":
    main()
