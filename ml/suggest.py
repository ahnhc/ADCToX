"""Search behind the first input screen (ml/form.py): disease names as you type, and diseases from symptoms or a sentence.

names(text)     instant, by spelling only (no model): registry conditions, disease profiles (Korean, everyday words, abbreviations),
                MONDO names of the installed index and the HIRA KCD Korean names. Exact > starts with > a word starts with > contains;
                Korean also by initial consonants (ㄷㄴ -> 당뇨). Runs on every key press.
semantic(text)  the SapBERT search of the installed index (ml/mondo_index.py), for names the spelling search misses; the form
                runs it in a background thread after a short pause in typing.
symptoms(text)  ranks the disease profiles (data/curated/disease_profiles/) against symptoms, history or a whole sentence, Korean or
                English: character 2/3-gram overlap per clause with each profile's names and symptom phrases (works on Korean word
                endings), plus BioLORD similarity of English text to each profile; names a sentence mentions directly come first.
A suggestion is (kind, value, label, detail, organs): kind 'reg' (registry id), 'mondo' (MONDO id, label = its name), 'text'
(typed or Korean text that goes through the usual linking). The form turns a 'mondo' pick into free text with that reading chosen.
"""
import glob, json, math, os, re, sys, threading, unicodedata

HANGUL = re.compile("[가-힣]")
ANIMAL = re.compile(r"\b(cattle|dog|horse|sheep|goat|pig|swine|chicken|poultry|rabbit|cervid|bovine|canine|feline|equine|medaka|zebrafish|non-human)\b", re.I)
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
TOKW = 4.0                      # weight of the content-word overlap (chosen on the dev half of symptom_eval_v0)
KO_END = sorted("습니다 었어요 았어요 했어요 이에요 에서 으로 이랑 하고 해서 어서 아서 어요 아요 해요 에요 예요 이고 이며 지만 는데 은데 인데 니다 을 를 이 가 은 는 에 도 만 과 와 랑 로 요 고 서 며 의".split(), key=len, reverse=True)
KO_STOP = {"있어", "있고", "있다", "없어", "먹어", "먹고", "하고", "해요", "받고", "받아", "자주", "계속", "요즘", "가끔", "많이", "조금", "그리고", "때문", "환자", "일주일", "번씩"}
EN_STOP = {"the", "and", "with", "has", "have", "had", "for", "from", "that", "this", "patient", "years", "year", "since", "takes", "taking", "history", "of", "on", "was", "were", "who", "his", "her", "she", "they"}
COVER = 0.8                     # a phrase fully contained in a clause scores like a cosine of 0.8
SYMPTOM_W = 2.0                 # weight of the BioLORD similarity next to the n-gram score (chosen on the dev half of symptom_eval_v0)
_LOCK = threading.Lock()


def norm(s):
    return " ".join(unicodedata.normalize("NFC", s).lower().replace("_", " ").split())


def _nospace(s): return re.sub(r"[\s·\-,()']", "", s)


def choseong(s):
    out = ""
    for c in s:
        o = ord(c) - 0xAC00
        out += CHO[o // 588] if 0 <= o < 11172 else c
    return out


def _is_cho(q): return bool(q) and all(c in CHO for c in q.replace(" ", ""))


# ------------------------------------------------------------------ data
_P = None


def profiles():
    """[{id, name, everyday, en, abbr, ko, ko_lay, symptoms_en, symptoms_ko}] from the app file or the repository."""
    global _P
    if _P is None:
        try:
            from __adc_data__ import _portable_data
            _P = _portable_data().get("profiles", [])
        except ImportError:
            _P = read_profiles(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "curated", "disease_profiles"))
    return _P


def read_profiles(root):
    """profiles_*.jsonl with the treatment cues of care_*.jsonl (care_en, care_ko) merged in by id."""
    rows = lambda pat: [json.loads(l) for f in sorted(glob.glob(os.path.join(str(root), pat))) for l in open(f, encoding="utf-8") if l.strip()]
    care = {c["id"]: c for c in rows("care_*.jsonl")}
    return [dict(p, care_en=care.get(p["id"], {}).get("care_en", p.get("care_en", [])), care_ko=care.get(p["id"], {}).get("care_ko", p.get("care_ko", []))) for p in rows("profiles_*.jsonl")]


_NH = []


def nonhuman():
    """MONDO ids under 'non-human animal disease' (MONDO:0005583): veterinary concepts the index still holds ('Alzheimer disease,
    domestic cat'). From the app file, or computed from the MONDO file in the repository."""
    if not _NH:
        try:
            from __adc_data__ import _portable_data
            _NH.append(set(_portable_data().get("nonhuman", [])))
        except ImportError:
            _NH.append(nonhuman_ids(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw_big", "mondo", "2026-10-07", "mondo.obo")))
    return _NH[0]


def nonhuman_ids(obo):
    children, cur = {}, None
    try:
        for line in open(obo, encoding="utf-8"):
            if line.startswith("id: "): cur = line[4:].strip()
            elif line.startswith("is_a: ") and cur: children.setdefault(line[6:].split()[0], []).append(cur)
    except OSError:
        return set()
    seen, st = set(), ["MONDO:0005583"]
    while st:
        n = st.pop()
        if n not in seen: seen.add(n); st += children.get(n, [])
    return seen


class Index:
    """every searchable string once: (normalized key, nospace key, choseong key, priority, suggestion)."""
    def __init__(self, RC):
        self.RC, self.rows, self.mondo_loaded, self.organs, self.words = RC, [], False, {}, None
        for i, r in RC._reg.items():
            org = r["organ_axes"].split(";")
            s = ("reg", i, r["label"], RC.KO.get(i, ""), org)
            for k in filter(None, [r["label"], RC.KO.get(i, ""), i.replace("_", " ")]): self._add(k, 3, s)
        self.by_id = {}
        for p in profiles():
            s = ("mondo", p["id"], p["name"][:1].upper() + p["name"][1:], (p.get("ko") or [""])[0], None)
            self.by_id[p["id"]] = s; pr = 2 if p.get("everyday", True) else 0
            for k in [p["name"]] + p.get("en", []) + p.get("ko", []) + p.get("ko_lay", []): self._add(k, pr, s)
            for k in p.get("abbr", []): self._add(k, pr, s)

    def _add(self, key, pr, s):
        n = norm(key)
        if n: self.rows.append((n, _nospace(n), choseong(_nospace(n)), pr, s))

    def load_mondo(self):
        """MONDO names and Korean KCD names of the installed index (strings only; no model is loaded). Called once, in the
        background when the screen opens; until it finishes the search uses the registry and the profiles."""
        with _LOCK_LOAD:
            if self.mondo_loaded: return
            try:
                import numpy as np, adc_runtime, mondo_index as MI
                keep, organs, nh = self.rows, {}, nonhuman()
                self.rows = []
                with np.load(adc_runtime.model_path("mondo_index.npz", MI.C + "mondo_index.npz"), allow_pickle=False) as d:
                    ids, names, axes = d["ids"].tolist(), d["names"].tolist(), d["axes"] > 0; axn = MI.AXES
                    for j, (t, n) in enumerate(zip(ids, names)):
                        if t in organs: continue
                        organs[t] = [axn[k] for k in np.flatnonzero(axes[j])]
                        if not n.startswith("obsolete") and t not in nh and not ANIMAL.search(n): self._add(n, 0, ("mondo", t, n[:1].upper() + n[1:], "", organs[t]))
                    if "abbr_keys" in d.files:                    # NLM LRABR abbreviations: every disease an abbreviation may mean
                        first = {}
                        for t, n in zip(ids, names): first.setdefault(t, n)
                        for k, v in zip(d["abbr_keys"].tolist(), d["abbr_vals"].tolist()):
                            for t in v.split(";")[:6]:
                                if t in first and t not in nh: self._add(k, 1, ("mondo", t, first[t][:1].upper() + first[t][1:], f"약어 {k.upper()}", organs.get(t, [])))
                    if "ko_keys" in d.files:
                        for k, v in zip(d["ko_keys"].tolist(), d["ko_vals"].tolist()):
                            if re.search(r"nos|[(),\[\]]", k) or len(k) > 20: continue
                            self._add(k, 1, ("text", k, k, v, None))
                mondo = self.rows; self.organs = organs
                self.rows = [r[:4] + ((r[4][:4] + (organs.get(r[4][1], []),)) if r[4][0] == "mondo" and r[4][4] is None else r[4],) for r in keep] + mondo
                self.by_id = {t: s[:4] + (organs.get(t, []),) for t, s in self.by_id.items()}
            except Exception:
                pass
            self.mondo_loaded = True


_IDX = {}
_LOCK_LOAD = threading.Lock()


def index(RC):
    if id(RC) not in _IDX: _IDX[id(RC)] = Index(RC)
    return _IDX[id(RC)]


# ------------------------------------------------------------------ names, as typed
def _score(q, qn, qc, row):
    key, ns, ch, pr, _ = row
    if qc:
        return 55 if ch.startswith(qc) else 30 if qc in ch else 0
    if key == q or (qn and ns == qn): return 100
    if key.startswith(q) or (qn and ns.startswith(qn)): return 80 - min(15, (len(key) - len(q)) // 3)
    if " " + q in " " + key: return 62 - min(10, len(key) // 10)
    words = q.split()
    if len(words) > 1 and all((" " + w) in (" " + key) for w in words): return 50
    if len(q) >= 2 and (q in key or (qn and qn in ns)): return 38 - min(10, len(key) // 10)
    return 0


NUMBERED = re.compile(r"^(.+?),?\s+(?:type\s+)?\d+[a-z]?(?:,.*)?$", re.I)     # gene-numbered subtypes: 'Alzheimer disease 5', 'Parkinson disease 12'


def _ranked(I, q):
    qn = _nospace(q) if HANGUL.search(q) else ""; qc = _nospace(q) if _is_cho(q) else ""; best = {}
    digits = any(c.isdigit() for c in q)
    for row in I.rows:
        s = _score(q, qn, qc, row)
        if s:
            s += row[3] * 6; v = (row[4][0], row[4][1])
            if not digits and NUMBERED.match(row[4][2]): s -= 30          # rare genetic subtypes only when a number is typed
            if s > best.get(v, (0,))[0]: best[v] = (s, -len(row[0]), row[4])
    return [x[2] for x in sorted(best.values(), key=lambda x: (-x[0], -x[1]))]


def _correct(I, q):
    """each word of a misspelt English query replaced by the closest word of the searchable names ('diabetis' -> 'diabetes')."""
    import difflib
    if I.words is None: I.words = sorted({w for r in I.rows for w in r[0].split() if len(w) >= 4 and w.isascii()})
    out = []
    for w in q.split():
        m = difflib.get_close_matches(w, I.words, n=1, cutoff=0.8) if len(w) >= 4 and w not in I.words else []
        out.append(m[0] if m else w)
    return " ".join(out)


def names(RC, text, limit=8):
    """spelling suggestions for the text being typed; the last comma-separated part counts when there are several.
    The same concept, or a Korean KCD name whose English name is already listed, is shown once."""
    q = norm(text.split(",")[-1])
    if not q: return []
    I = index(RC); out = _ranked(I, q)
    if len(out) < 3 and len(q) >= 4 and q.isascii():                  # a typo
        c = _correct(I, q)
        if c != q: out += [s for s in _ranked(I, c) if all((x[0], x[1]) != (s[0], s[1]) for x in out)]
    seen, keep = set(), []
    shown = {norm(s[2]) for s in out}
    for s in out:
        k1, k2 = norm(s[2]), norm(s[3]) if s[0] == "text" else None
        if k1 in seen or (k2 and k2 in seen): continue
        m = NUMBERED.match(s[2])
        if m and not any(c.isdigit() for c in q) and norm(m.group(1)) in shown: continue    # the base disease is listed: hide its subtypes
        seen.add(k1); seen.add(norm(s[3])) if s[3] else None; keep.append(s)
        if len(keep) == limit: break
    return [_with_organs(RC, s) for s in keep]


def parts(RC, text):
    """words of a space-separated input that are each a known name or abbreviation by themselves ('asd adhd' -> ['asd', 'adhd']);
    [] when the input is one name ('heart failure') or a word is unknown. The form offers to add them separately."""
    words = norm(text.split(",")[-1]).split()
    if len(words) < 2: return []
    I = index(RC); keys = {r[0] for r in I.rows}
    if " ".join(words) in keys: return []
    return words if all(w in keys for w in words) else []


def _with_organs(RC, s):
    kind, val, label, detail, org = s
    if org is None and kind == "mondo": org = index(RC).organs.get(val)
    return (kind, val, label, detail, org or [])


def semantic(RC, text, k=5):
    """SapBERT neighbours of the typed text in the installed index -> suggestions (slow the first time: loads the encoder)."""
    q = text.split(",")[-1].strip()
    if len(q) < 2: return []
    with _LOCK:
        import mondo_index as MI
        en = RC.english([q])[0]
        lk = MI.link([en])[0]
        out, seen = [], set()
        for r in [dict(mondo=lk["mondo"], name=lk["name"], organs=lk["axes"], sim=lk["sim"])] + lk.get("readings", []):
            if r["mondo"] in seen or r["mondo"] in nonhuman() or r.get("sim", 1) < 0.75: continue        # = mondo_index.THETA
            seen.add(r["mondo"]); name = r["name"]
            out.append(("mondo", r["mondo"], name[:1].upper() + name[1:], "", r.get("organs") or MI.concept(r["mondo"])[1]))
        if lk.get("hpo"):
            h = lk["hpo"]; out.append(("mondo", h["hpo"], h["name"][:1].upper() + h["name"][1:], "증상", h["organs"]))
        return out[:k]


# ------------------------------------------------------------------ symptoms and sentences
SPLIT = re.compile(r"[,.;/\n]|\band\b|\bwith\b|그리고|이고|이며|하고|있고|있으며|있어요|있습니다|인데|는데|해서|라서|이랑|랑|및|또는")


def clauses(text):
    parts = [norm(p) for p in SPLIT.split(text)]
    return [p for p in parts if len(_nospace(p)) >= 2] or ([norm(text)] if norm(text) else [])


def _grams(s, ns=(2, 3)):
    s = _nospace(norm(s)); out = {}
    for n in ns:
        for i in range(max(0, len(s) - n + 1)): out[s[i:i + n]] = out.get(s[i:i + n], 0) + 1
    return out


class Symptoms:
    def __init__(self):
        P = [p for p in profiles() if p.get("everyday", True)]
        self.P = P; self.phr = []                                    # (profile index, phrase, is_name, grams)
        df = {}
        for i, p in enumerate(P):
            for ph, is_name in [(x, True) for x in [p["name"]] + p.get("en", []) + p.get("ko", []) + p.get("ko_lay", []) + p.get("abbr", [])] + \
                               [(x, False) for x in p.get("symptoms_en", []) + p.get("symptoms_ko", []) + p.get("care_en", []) + p.get("care_ko", [])]:
                g = _grams(ph)
                if g: self.phr.append((i, ph, is_name, g))
        for _, _, _, g in self.phr:
            for k in g: df[k] = df.get(k, 0) + 1
        N = len(self.phr); self.idf = {k: math.log((1 + N) / (1 + v)) + 1 for k, v in df.items()}
        self.post = {}
        for j, (_, _, _, g) in enumerate(self.phr):
            for k in g: self.post.setdefault(k, []).append(j)
        self.norms = [math.sqrt(sum((c * self.idf[k]) ** 2 for k, c in g.items())) for _, _, _, g in self.phr]
        self.cden = [sum(c * self.idf[k] ** 2 for k, c in g.items()) for _, _, _, g in self.phr]
        self._E = None
        self.docs = [_nospace(norm(" ".join(ph for i2, ph, _, _ in self.phr if i2 == i))) for i in range(len(P))]
        self.tok_df = {}

    def _tok_idf(self, t):
        if t not in self.tok_df: self.tok_df[t] = sum(1 for d in self.docs if t in d)
        df = self.tok_df[t]
        return math.log(len(self.docs) / df) if df else 0.0

    def tokens(self, text):
        """content words of the text: Korean particles and verb endings stripped ('투석을' -> '투석'), English stop words dropped."""
        out = []
        for w in re.findall(r"[가-힣]+|[a-z][a-z0-9]+", norm(text)):
            if HANGUL.search(w):
                for e in KO_END:                                     # the longest ending only: 중이고 is not 중이 (middle ear)
                    if w.endswith(e):
                        if len(w) - len(e) >= 2: w = w[:-len(e)]
                        break
                if len(w) >= 2 and w not in KO_STOP: out.append(w)
            elif len(w) >= 3 and w not in EN_STOP: out.append(w)
        return list(dict.fromkeys(out))

    def _match(self, clause):
        """-> {phrase index: (cosine, coverage)} for phrases sharing n-grams with the clause; coverage = the idf-weighted share of
        the phrase's n-grams found in the clause, so a short symptom inside a long sentence still counts."""
        g = _grams(clause); qn = math.sqrt(sum((c * self.idf.get(k, 0)) ** 2 for k, c in g.items())) or 1; acc, cov = {}, {}
        for k, c in g.items():
            w = c * self.idf.get(k, 0)
            for j in self.post.get(k, ()):
                pc = self.phr[j][3][k]; acc[j] = acc.get(j, 0) + w * pc * self.idf[k]; cov[j] = cov.get(j, 0) + min(c, pc) * self.idf[k] ** 2
        return {j: (v / (qn * self.norms[j]), cov[j] / self.cden[j]) for j, v in acc.items()}

    def embeddings(self):
        """BioLORD vectors of 'name: symptoms' per profile, cached next to the models (computed once, about 10 s on a CPU)."""
        if self._E is None:
            import numpy as np, hashlib, vulnerability_model as VM, adc_runtime
            texts = [p["name"] + ": " + ", ".join(p.get("symptoms_en", []) + p.get("care_en", [])) for p in self.P]
            key = hashlib.sha256(("\n".join(texts) + str(adc_runtime.bundle_identity())).encode()).hexdigest()[:16]
            home = adc_runtime.active_directory()
            path = os.path.join(str(home.parent.parent) if home else "/tmp", f"profile_biolord_{key}.npy")
            try: self._E = np.load(path)
            except (OSError, ValueError):
                self._E = VM._st(texts).astype(np.float32)
                try: np.save(path, self._E)
                except OSError: pass
        return self._E

    def search(self, text, semantic=True, limit=8):
        """-> [(profile, score, matched phrases)] best first."""
        cl = clauses(text)
        if not cl: return []
        hit = {}                                                     # profile -> {phrase: best value over the clauses}
        for c in cl:
            for j, (cos, cov) in self._match(c).items():
                i, ph, is_name, g = self.phr[j]
                v = max(cos, COVER * cov if len(g) >= 3 else 0.0) * (1.6 if is_name else 1.0)
                if v >= 0.35 and v > hit.setdefault(i, {}).get(ph, 0): hit[i][ph] = v
        score, why = [0.0] * len(self.P), [[] for _ in self.P]
        for i, d in hit.items():
            top = sorted(d.items(), key=lambda x: -x[1])[:4]; score[i] = sum(v for _, v in top); why[i] = [ph for ph, _ in top]
        toks = [(t, self._tok_idf(t)) for t in self.tokens(text)]; total = sum(w for _, w in toks)
        if TOKW and total:                                          # share of the text's content words the profile mentions
            for i, d in enumerate(self.docs):
                got = [t for t, w in toks if w and t in d]
                if got:
                    score[i] += TOKW * sum(w for t, w in toks if t in got) / total; why[i] += [t for t in got if not any(t in _nospace(x) for x in why[i])]
        en = " ".join(cl) if not HANGUL.search(text) else ""        # Korean: n-grams only (mapping Korean clauses to English phrases did not help on the test half)
        if semantic and en:
            try:
                import numpy as np, vulnerability_model as VM
                with _LOCK: q = VM._st([en])[0]; sims = self.embeddings() @ q
                for i, s in enumerate(sims.tolist()): score[i] += SYMPTOM_W * max(0.0, s - 0.3) / 0.7
            except Exception:
                pass
        order = sorted(range(len(self.P)), key=lambda i: -score[i])
        return [(self.P[i], score[i], why[i]) for i in order[:limit] if score[i] > 0.15]


_SYM = []


def symptoms(RC, text, semantic=True, limit=8):
    """suggestions from symptoms / a sentence: names the text mentions directly first, then diseases ranked by symptoms."""
    if not _SYM: _SYM.append(Symptoms())
    I = index(RC); out, seen = [], set()
    for c in clauses(text):                                           # a clause that is itself a disease name ('당뇨', 'copd')
        for s in names(RC, c, limit=1):
            if (s[0], s[1]) not in seen and _score(norm(c), _nospace(norm(c)) if HANGUL.search(c) else "", "", (norm(s[2]), _nospace(norm(s[2])), "", 0, s)) >= 0:
                hit = [r for r in I.rows if (r[4][0], r[4][1]) == (s[0], s[1]) and (r[0] == norm(c) or r[1] == _nospace(norm(c)))]
                if hit: seen.add((s[0], s[1])); out.append((s, "입력한 이름"))
    for p, sc, why in _SYM[0].search(text, semantic=semantic, limit=limit):
        s = I.by_id[p["id"]]
        if (s[0], s[1]) in seen: continue
        seen.add((s[0], s[1])); out.append((_with_organs(RC, s), ", ".join(dict.fromkeys(why))[:60]))
    return out[:limit]
