"""Benchmark of the disease judge: the same questions for the untuned Gemma, each tuned model, and the app pipeline.

    CUDA_VISIBLE_DEVICES=0 ADC_RESEARCH_MODE=1 python ml/bench_judge.py --system base
    CUDA_VISIBLE_DEVICES=0 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<model folder> python ml/bench_judge.py --system single --name j5s7 [--card v5s7]
    CUDA_VISIBLE_DEVICES=0 ADC_RESEARCH_MODE=1 ADCTOX_CACHE=<model folder> python ml/bench_judge.py --system app --name app_j5s7
    python ml/bench_judge.py --table base j5s7 app_j5s7 [--ref base] [--test]

Questions (fixed, never training text; ml/tuning_ledger.py checks the overlap before every training run):
  gold     600 English queries (data/curated/disease_linking: canonical, synonym, abbrev, typo, lay, ambiguous, non_disease,
           invalid) with two-annotator MONDO concepts and organs; the same 600 in Korean (judge2/gen/koeval_*)
  symptom  data/curated/disease_profiles/symptom_eval_v0.jsonl: patient or clinician descriptions -> the disease profile
Split: dev / test by query group (ml/eval_linking.split_of) and by target (symptoms). Dev unless --test; test once at the end.

Systems:
  base     Gemma 4 E2B as released (google/gemma-4-E2B, the revision the judge is tuned from), no tuning: a few-shot prompt
           asks for the standard disease name and the organs; the name is linked to MONDO by exact name or exact synonym.
           Few-shot examples come from training profiles outside the gold and symptom sets (asserted).
  single   one tuned Gemma judge alone: valid head -> aligned vector -> nearest MONDO name (cosine >= THETA) -> that concept's
           organs, else the organ head; symptoms from the sym head. No BioLORD, no SapBERT encoder.
  app      the shipped pipeline (recommend.resolve: registry -> SapBERT/MONDO -> Gemma judge); no concept output.
Metrics: organ macro-F1 (13 axes), concept top-1, coverage, false acceptance of invalid and ambiguous inputs, by category;
symptom top-1/top-3 (recorded, not a target: the profile sentences make it easy to overfit). --table [--organs] prints all systems with a paired bootstrap against --ref.
-> ml/results/benchmarks/bench_<name>.json (per-question predictions and scores)
"""
import json, os, re, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P, eval_linking as EL, eval_a4 as E4

OUT = P.REPO + "ml/results/benchmarks/"
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic",
        "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
THETA = float(os.environ.get("BENCH_THETA", 0.7))     # align cosine needed to take the linked concept's organs
CATS = ("canonical", "synonym", "abbrev", "typo", "lay")

SHOTS = [  # (input, standard name or invalid/ambiguous, organs); training profiles outside the gold and symptom sets
    ("trigeminal neuralgia", "trigeminal neuralgia", ["neurologic"]),
    ("바이러스성 결막염", "viral conjunctivitis", ["ocular", "infectious_immune"]),
    ("오늘 점심 뭐 먹지", "invalid", []),
    ("low vitamin B12", "vitamin B12 deficiency", ["haematologic", "neurologic", "metabolic_endocrine"]),
    ("자가면역 용혈성 빈혈", "autoimmune hemolytic anemia", ["haematologic", "infectious_immune"]),
    ("MR", "ambiguous", []),
    ("mouth cancer", "oral cavity cancer", ["gastrointestinal"]),
    ("당뇨 때문에 발이 저려요", "diabetic neuropathy", ["neurologic", "metabolic_endocrine"]),
    ("asdf qwer", "invalid", []),
    ("무좀", "superficial mycosis", ["dermatologic", "infectious_immune"]),
]
SHOT_IDS = ["MONDO:0008599", "MONDO:0043541", "MONDO:0020696", "MONDO:0020108", "MONDO:0005515", "MONDO:0006626", "MONDO:0024268"]
SYM_SHOTS = [
    ("Sudden stabbing electric pain on one side of my face when I chew or touch my cheek.", ["trigeminal neuralgia", "cluster headache", "dental abscess"]),
    ("발가락 사이가 하얗게 벗겨지고 가려워요. 발바닥에도 각질이 일어나요.", ["superficial mycosis", "contact dermatitis", "psoriasis"]),
]
HEAD = ("Task: read what a patient or clinician typed. If it names a disease, symptom, finding or medical history, give the standard "
        "English disease name and the organ systems it directly affects. Organ systems: " + ", ".join(AXES) + ". If the text is not "
        "medical, the name is invalid. If it could mean several different diseases, the name is ambiguous.\n\n")
SYM_HEAD = "Task: a patient's or clinician's description. Name the three most likely diseases, most likely first.\n\n"


def questions():
    Q, gold, groups, ko = E4.gold()
    SE = [json.loads(l) for l in open(P.REPO + "data/curated/disease_profiles/symptom_eval_v0.jsonl", encoding="utf-8") if l.strip()]
    return Q, gold, groups, ko, SE


def questions_sha():
    """hash of the benchmark questions and gold labels, so a stored result is reused only for the same questions."""
    import hashlib, tuning_ledger as TL
    m = TL.manifest(TL.EVAL_DATA); return hashlib.sha256(json.dumps({k: v["sha"] for k, v in m.items()}, sort_keys=True).encode()).hexdigest()[:16]


def check_shots(Q, ko, SE):
    import linking_models as LM, tuning_ledger as TL
    from build_linking_pools import read_obo
    T = read_obo(); held = LM.gold_held(T); targets = {s["target"] for s in SE} | {a for s in SE for a in s.get("also_ok", [])}
    ev = {TL.norm(q["query"]) for q in Q} | {TL.norm(t) for t in ko.values() if t} | {TL.norm(s["query"]) for s in SE}
    for t in SHOT_IDS: assert t not in held and t not in targets, t
    for x, *_ in SHOTS + [(s[0],) for s in SYM_SHOTS]: assert TL.norm(x) not in ev, x


# ---------------------------------------------------------------- systems

class Base:
    """untuned Gemma 4 E2B, few-shot generation."""
    def __init__(self):
        import torch, transformers as T, gemma_judge as GJ
        from huggingface_hub import snapshot_download
        path = snapshot_download(GJ.GEMMA, revision=GJ.REV, cache_dir=os.environ.get("GEMMA_CACHE", "/data/hyeongchanahn/hf/hub"))
        self.tok = T.AutoTokenizer.from_pretrained(path); self.tok.padding_side = "left"
        self.lm = T.AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16).to("cuda:0").eval(); self.torch = torch
        shots = "".join(f"Input: {x}\nName: {n}\nOrgans: {', '.join(o) or 'none'}\n\n" for x, n, o in SHOTS)
        self.prompt = HEAD + shots + "Input: {}\nName:"
        self.sym_prompt = SYM_HEAD + "".join(f"Description: {d}\nDiseases: {'; '.join(n)}\n\n" for d, n in SYM_SHOTS) + "Description: {}\nDiseases:"
        self.names = None

    def gen(self, prompts, n=40, bs=16):
        out = []
        for i in range(0, len(prompts), bs):
            enc = self.tok(prompts[i:i + bs], return_tensors="pt", padding=True).to("cuda:0")
            with self.torch.no_grad():
                g = self.lm.generate(**enc, max_new_tokens=n, do_sample=False, pad_token_id=self.tok.pad_token_id)
            out += self.tok.batch_decode(g[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        return out

    def link(self, name):
        """standard name -> MONDO id by exact name or exact synonym (normalised)."""
        if self.names is None:
            from build_linking_pools import read_obo
            import tuning_ledger as TL
            T = read_obo(); self.names = {}
            for t, x in T.items():
                for s in [x["name"]] + list(x.get("syn", [])):
                    self.names.setdefault(TL.norm(s), t)
        import tuning_ledger as TL
        return self.names.get(TL.norm(name))

    def gold(self, texts):
        rows = []
        for t, g in zip(texts, self.gen([self.prompt.format(t) for t in texts])):
            name = g.split("\n")[0].strip(); m = re.search(r"Organs:\s*([^\n]*)", g)
            organs = [a for a in AXES if m and re.search(rf"\b{a}\b", m.group(1))]
            if name.lower() in ("invalid", "ambiguous", ""): rows.append(dict(raw=g[:160], concept=None, organs=[])); continue
            rows.append(dict(raw=g[:160], concept=self.link(name), organs=organs))
        return rows

    def symptoms(self, texts, prof_ids):
        out = []
        for g in self.gen([self.sym_prompt.format(t) for t in texts], n=48):
            names = [s.strip() for s in g.split("\n")[0].split(";") if s.strip()][:5]
            out.append(dict(raw=g[:160], ranked=[c for c in (self.link(n) for n in names) if c]))
        return out


class Single:
    """one tuned Gemma judge, alone."""
    def __init__(self):
        import gemma_runtime as GR, mondo_index as MI
        self.GR, self.MI = GR, MI; MI.link(["x"]); Z = MI._IDX
        self.E, self.ids = Z["E"].astype(np.float32), Z["_ids"]

    def gold(self, texts):
        o = self.GR.outputs(list(texts)); _, _, (_, _, _, thr, _) = self.GR.load(); rows = []
        S = o["vec"] @ self.E.T; j = S.argmax(1); s = S.max(1)
        for k in range(len(texts)):
            if not o["valid_ok"][k]: rows.append(dict(concept=None, organs=[], valid=float(o["valid"][k]))); continue
            c = str(self.ids[j[k]]) if s[k] >= THETA else None
            lo = list(self.MI.concept(c)[1]) if c else []
            jo = [AXES[a] for a in np.where(o["organ"][k] >= thr)[0]]
            rows.append(dict(concept=c, organs=lo or jo, valid=float(o["valid"][k]), sim=float(s[k])))
        return rows

    def symptoms(self, texts, prof_ids):
        o = self.GR.outputs(list(texts)); ids = o["profiles"]
        return [dict(ranked=[ids[a] for a in np.argsort(-p)[:5]]) for p in o["sym"]]


class Scratch:
    """the from-scratch judge (ml/scratch_judge.py) in $SCRATCH_DIR."""
    def __init__(self):
        import scratch_judge as SJ
        self.SJ, self.dir = SJ, os.environ["SCRATCH_DIR"].rstrip("/") + "/"

    def gold(self, texts): return self.SJ.judge(list(texts), self.dir)

    def symptoms(self, texts, prof_ids): return None


class App:
    """the shipped pipeline."""
    def __init__(self):
        import recommend as RC
        self.RC = RC

    def gold(self, texts):
        rows = []
        for q in texts:
            self.RC.FALLBACK = {}; _, _, _, notes, pc = self.RC.resolve([q])
            rows.append(dict(concept=None, organs=sorted(set().union(*[o for c, o, _ in pc if c == q]) if pc else []), how=dict(notes).get(q, "")))
        return rows

    def symptoms(self, texts, prof_ids): return None


# ---------------------------------------------------------------- scoring

def sym_split(t):
    import hashlib
    return "dev" if int(hashlib.sha256(t.encode()).hexdigest(), 16) % 2 == 0 else "test"


def score(per, split):
    Q, gold, groups, ko, SE = questions(); ix = [i for i, g in enumerate(groups) if EL.split_of(g) == split]; res = {}
    for lang in ("en", "ko"):
        rows = per[lang]; jx = [i for i in ix if rows[i] is not None]
        pred = [((r or {}).get("concept"), (r or {}).get("organs", [])) for r in rows]
        m = EL.metrics(pred, gold, jx)
        res[lang] = dict(n=len(jx), **{k: (round(m[k], 3) if m[k] is not None else None) for k in ("macro_f1", "concept_acc", "coverage", "false_accept_invalid", "accept_ambiguous")},
                         by_category={c: round(EL.metrics(pred, gold, [i for i in jx if gold[i]["category"] == c])["macro_f1"], 3) for c in CATS})
    if per.get("sym"):
        r = []
        for s, p in zip(SE, per["sym"]):
            if sym_split(s["target"]) != split: continue
            ok = {s["target"], *s.get("also_ok", [])}; rk = next((k + 1 for k, c in enumerate(p["ranked"]) if c in ok), None); r.append(rk)
        res["symptom"] = dict(n=len(r), top1=round(float(np.mean([x == 1 for x in r])), 3), top3=round(float(np.mean([x is not None and x <= 3 for x in r])), 3))
    return res


def run(system, name, card=None):
    Q, gold, groups, ko, SE = questions(); check_shots(Q, ko, SE); t0 = time.time()
    S = dict(base=Base, single=Single, app=App, scratch=Scratch)[system](); per = {}
    per["en"] = S.gold([q["query"] for q in Q])
    kq = [ko.get(q["qid"]) for q in Q]; got = S.gold([t for t in kq if t]); it = iter(got)
    per["ko"] = [next(it) if t else None for t in kq]
    per["sym"] = S.symptoms([s["query"] for s in SE], None)
    import gemma_judge as GJ
    info = dict(name=name, system=system, cache=(os.environ.get("SCRATCH_DIR") if system == "scratch" else P.CACHE if system != "base" else None), minutes=round((time.time() - t0) / 60, 1),
                revision=GJ.REV, questions=questions_sha(),
                theta=THETA if system == "single" else None, shots=SHOTS if system == "base" else None)
    res = dict(dev=score(per, "dev")); json.dump(dict(info, per=per, scores=res), open(OUT + f"bench_{name}.json", "w"), ensure_ascii=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    if card:
        import tuning_ledger as TL
        d = res["dev"]; TL.add_bench(card, f"{system} (dev)", dict(en=d["en"]["macro_f1"], ko=d["ko"]["macro_f1"], concept_en=d["en"]["concept_acc"],
                                                                     invalid_accept=d["en"]["false_accept_invalid"], symptom_top3=d.get("symptom", {}).get("top3")))
        TL.render()


def table(names, ref, split, organs=False):
    Q, gold, groups, ko, SE = questions(); ix = [i for i, g in enumerate(groups) if EL.split_of(g) == split]
    B = {n: json.load(open(OUT + f"bench_{n}.json")) for n in names}
    print(f"split {split}")
    print(f"{'system':16} {'EN F1':>7} {'KO F1':>7} {'EN conc':>8} {'KO conc':>8} {'inv acc':>8} {'amb acc':>8}   Δ vs {ref} [95%] EN | KO")
    for n in names:
        s = score(B[n]["per"], split); dl = ""
        if ref and n != ref:
            for lang in ("en", "ko"):
                pa = [((r or {}).get("concept"), (r or {}).get("organs", [])) for r in B[n]["per"][lang]]
                pb = [((r or {}).get("concept"), (r or {}).get("organs", [])) for r in B[ref]["per"][lang]]
                jx = [i for i in ix if B[n]["per"][lang][i] is not None and B[ref]["per"][lang][i] is not None]
                b = EL.boot(pa, pb, gold, jx, groups); dl += f"{b['delta']:+.3f} [{b['lo']:+.3f}, {b['hi']:+.3f}]" + (" | " if lang == "en" else "")
        f = lambda v: "-" if v is None else f"{v:.3f}"
        print(f"{n:16} {f(s['en']['macro_f1']):>7} {f(s['ko']['macro_f1']):>7} {f(s['en']['concept_acc']):>8} {f(s['ko']['concept_acc']):>8} "
              f"{f(s['en']['false_accept_invalid']):>8} {f(s['en']['accept_ambiguous']):>8}   {dl}")
    if organs:
        print(f"\norgan F1 ({split}); * = at least 0.95")
        print(f"{'organ':20}" + "".join(f"{n[:12] + ' ' + l:>17}" for n in names for l in ("en", "ko")))
        M = {(n, l): EL.metrics([((r or {}).get("concept"), (r or {}).get("organs", [])) for r in B[n]["per"][l]], gold, [i for i in ix if B[n]["per"][l][i] is not None])["per_organ_f1"] for n in names for l in ("en", "ko")}
        for ax in AXES:
            print(f"{ax:20}" + "".join(f"{'-' if M[(n, l)][ax] is None else format(M[(n, l)][ax], '.2f') + ('*' if M[(n, l)][ax] >= 0.95 else ' '):>17}" for n in names for l in ("en", "ko")))


if __name__ == "__main__":
    a = sys.argv; split = "test" if "--test" in a else "dev"
    if "--table" in a:
        rest = a[a.index("--table") + 1:]; names = rest[: next((k for k, x in enumerate(rest) if x.startswith("--")), len(rest))]
        table(names, a[a.index("--ref") + 1] if "--ref" in a else None, split, "--organs" in a)
    else:
        sysname = a[a.index("--system") + 1]; name = a[a.index("--name") + 1] if "--name" in a else sysname
        run(sysname, name, a[a.index("--card") + 1] if "--card" in a else None)
