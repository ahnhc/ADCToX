"""Stage-5 case-level validation on JADER, the Japanese spontaneous adverse-event database (PMDA), which carries each case's
primary diseases / medical history (原疾患等) next to the suspect drug and the reported events.

    /data/hyeongchanahn/envs/adctox/bin/python -I ml/validate_jader.py /data/hyeongchanahn/adctox/raw/jader/<date>/

Results using this database must state: "本解析は医薬品医療機器総合機構（PMDA）の医薬品副作用データベース（JADER）を利用した結果である"
(this analysis uses the PMDA Japanese Adverse Drug Event Report database, JADER). The raw files are kept local and not redistributed.

What this can test that FAERS could not: a patient attribute. The recommender's premise is that a patient vulnerable in organ o is
worse served by an ADC whose label warns on o. Unit = (case, organ o) for every case with exactly one of the 14 ADCs as suspect drug:
    y = an adverse event in organ o was reported for the case
    v = the case's history includes a condition of organ o (malignancies excluded: the indication itself is in 原疾患)
    L = the ADC's label level on o (boxed 2, section 5 1, none 0; ml/drug_evidence.py)
Pre-declared analyses (fixed before the data were read):
  1. vulnerable patients: among pairs with v = 1, AUROC of L for y      -> the recommender's order for a patient vulnerable in o
  2. effect modification: odds ratio of y for L > 0, in v = 1 vs v = 0  -> does vulnerability amplify a warned toxicity?
  3. patient information: out-of-fold logistic y ~ L  vs  y ~ L + v + v*L (folds by case), paired AUROC difference
  4. calibration of model 3b out of fold: Brier vs base rate, calibration-in-the-large, slope
  5. per organ, drug order: among cases vulnerable in o, Spearman(L_o, share of cases reporting an o event) over the ADCs
A case's latest report version (報告回数) is used. Bootstrap over cases. Limits, stated with every result: spontaneous reports have no denominator (shares are among REPORTED cases,
not incidences), reporting is stimulated by warnings, and history fields are incomplete.

Terms are MedDRA/J (Japanese). Organ mapping: kanji-root rules below (auditable; first match wins, malignancy and constitutional
terms excluded), else the nearest English PT in data/processed/pt_soc_dictionary.json by BGE-M3 at cosine >= 0.80, else unmapped.
The run prints the most frequent terms with their mapping so the rules can be audited.
"""
import glob, json, os, re, sys
import numpy as np, pandas as pd
sys.path[:0] = ["/home/hyeongchanahn/CONI/adctox/ml", "/home/hyeongchanahn/CONI/adctox/src"]
R = "/home/hyeongchanahn/CONI/adctox/"
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular",
        "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
EXCLUDE = re.compile(r"癌|がん|肉腫|リンパ腫|白血病|骨髄腫|腫瘍|転移|新生物|悪性|ホジキン|骨髄異形成|死亡|疾患進行|病勢進行|発熱(?!性好中球)|倦怠|疲労|無力")
RULES = [   # order matters: a term takes the first organ whose pattern it contains
    ("haematologic", r"好中球|血小板|貧血|白血球|汎血球|骨髄抑制|骨髄機能|骨髄不全|リンパ球数減少|リンパ球減少|ヘモグロビン|赤血球|血球減少|播種性血管内凝固|血球貪食"),
    ("hepatic", r"肝|胆|黄疸|ビリルビン|トランスアミナーゼ|アスパラギン酸アミノ|アラニンアミノ|γ－ＧＴＰ|γ-GTP|ＡＳＴ|ＡＬＴ|AST|ALT|静脈閉塞|類洞閉塞"),
    ("gastrointestinal", r"悪心|嘔吐|下痢|口内炎|大腸炎|腸炎|膵|便秘|腹痛|消化|胃|腸|粘膜の炎症|粘膜炎|食道|口腔|アミラーゼ|リパーゼ|腹水"),
    ("pulmonary", r"間質|肺臓炎|呼吸|胸水|低酸素|咳|喘息|肺塞栓|肺障害|肺線維|器質化肺炎"),
    ("infectious_immune", r"感染|敗血|肺炎|帯状疱疹|ウイルス|真菌|カンジダ|サイトメガロ|菌血|蜂巣炎|膿瘍|過敏|アナフィラキシー|インフュージョン|注入に伴う反応|輸注|免疫"),
    ("pulmonary", r"肺|気管支"),
    ("metabolic_endocrine", r"糖尿|尿酸|脂質|脂血|コレステロール|トリグリセリド|痛風"),      # before renal: 糖尿病 and 尿酸 contain 尿
    ("renal", r"腎|尿|クレアチニン|ネフ|透析"),
    ("cardiovascular", r"心|駆出率|ＱＴ|QT|不整脈|頻脈|徐脈|血圧|出血|浮腫|血栓|塞栓|静脈炎|毛細血管漏出|血管|動脈"),
    ("neurologic", r"神経|ニューロパチー|脳|痙攣|頭痛|めまい|浮動性|意識|錯感覚|感覚鈍麻|麻痺|味覚"),
    ("ocular", r"眼|角膜|視|結膜|網膜|霧視|ドライアイ|緑内障|白内障|涙"),
    ("dermatologic", r"皮膚|発疹|皮疹|紅斑|そう痒|脱毛|蕁麻疹|スティーブンス|スティーヴンス|中毒性表皮|手掌|爪|水疱"),
    ("metabolic_endocrine", r"糖|ナトリウム|カリウム|カルシウム|マグネシウム|低リン|高リン|電解質|甲状腺|代謝|腫瘍崩壊|食欲|脱水|尿酸"),
    ("musculoskeletal", r"筋|関節|骨|背部痛|四肢痛"),
    ("otologic", r"耳|難聴|聴"),
]
# ADC suspect-drug names (医薬品（一般名）), matched after removing spaces; katakana per the Japanese package inserts
ADC_JA = {"trastuzumab-emtansine": "トラスツズマブエムタンシン", "trastuzumab-deruxtecan": "トラスツズマブデルクステカン",
          "datopotamab-deruxtecan": "ダトポタマブデルクステカン", "brentuximab-vedotin": "ブレンツキシマブベドチン",
          "enfortumab-vedotin": "エンホルツマブベドチン", "polatuzumab-vedotin": "ポラツズマブベドチン", "tisotumab-vedotin": "チソツマブベドチン",
          "telisotuzumab-vedotin": "テリソツズマブベドチン", "gemtuzumab-ozogamicin": "ゲムツズマブオゾガマイシン",
          "inotuzumab-ozogamicin": "イノツズマブオゾガマイシン", "sacituzumab-govitecan": "サシツズマブゴビテカン",
          "mirvetuximab-soravtansine": "ミルベツキシマブソラブタンシン", "loncastuximab-tesirine": "ロンカスツキシマブテシリン",
          "pivekimab-sunirine": "ピベキマブスニリン"}


def norm(s): return re.sub(r"[\s　・･]", "", str(s))


class OrganMapper:
    def __init__(self, use_embedding=True):
        self.cache, self.how = {}, {}; self.emb = None
        if use_embedding:
            try:
                from adctox.taxonomy import Taxonomy
                self.tax = Taxonomy(); self.tax.load_pt_dictionary(R + "data/processed/pt_soc_dictionary.json")
                self.pts = list(json.load(open(R + "data/processed/pt_soc_dictionary.json"))["terms"]); self.emb = "lazy"
            except Exception: self.emb = None

    def _embed_map(self, terms):
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer("BAAI/bge-m3", device="cuda:0" if __import__("torch").cuda.is_available() else "cpu")
        if not isinstance(self.emb, np.ndarray): self.emb = m.encode(self.pts, batch_size=256, normalize_embeddings=True, convert_to_numpy=True)
        Q = m.encode(terms, batch_size=256, normalize_embeddings=True, convert_to_numpy=True); S = Q @ self.emb.T; out = {}
        for t, s in zip(terms, S):
            k = int(s.argmax()); ax = self.tax.resolve_term_only(self.pts[k])[0] if s[k] >= 0.80 else None
            out[t] = (ax if ax in AXES else None, f"bge-m3 -> {self.pts[k]} ({s[k]:.2f})")
        return out

    def map(self, terms):
        todo = []
        for t in set(terms) - set(self.cache):
            n = norm(t)
            if EXCLUDE.search(n): self.cache[t], self.how[t] = None, "excluded (malignancy / constitutional)"; continue
            hit = next((ax for ax, pat in RULES if re.search(pat, n)), None)
            if hit: self.cache[t], self.how[t] = hit, "rule"
            else: todo.append(t)
        if todo and self.emb is not None:
            for t, (ax, how) in self._embed_map(todo).items(): self.cache[t], self.how[t] = ax, how
        for t in todo: self.cache.setdefault(t, None); self.how.setdefault(t, "unmapped")
        return {t: self.cache[t] for t in terms}


def read_jader(d):
    """the four JADER tables; column names found by substring so minor header changes do not break it."""
    def load(prefix):
        f = sorted(glob.glob(os.path.join(d, f"{prefix}*.csv")) + glob.glob(os.path.join(d, "**", f"{prefix}*.csv"), recursive=True))
        if not f: raise FileNotFoundError(f"no {prefix}*.csv under {d}")
        for enc in ("cp932", "utf-8-sig", "utf-8"):
            try: return pd.read_csv(f[-1], encoding=enc, dtype=str, low_memory=False)
            except UnicodeDecodeError: continue
        raise UnicodeDecodeError(f"cannot decode {f[-1]}")
    def col(df, key):                       # exact name first; '有害事象' must not resolve to '有害事象連番'
        if key in df.columns: return key
        return next(c for c in df.columns if key in c and "連番" not in c)
    drug, reac, hist = load("drug"), load("reac"), load("hist")
    def latest(df):                         # a case is re-reported (報告回数 01, 02, ...); keep its latest version only
        k, n = col(df, "識別番号"), col(df, "報告回数"); last = df.groupby(k)[n].transform("max"); return df[df[n] == last]
    drug, reac, hist = latest(drug), latest(reac), latest(hist)
    D = pd.DataFrame(dict(case=drug[col(drug, "識別番号")], role=drug[col(drug, "関与")], name=drug[col(drug, "一般名")].map(norm)))
    Rr = pd.DataFrame(dict(case=reac[col(reac, "識別番号")], term=reac[col(reac, "有害事象")].astype(str)))
    H = pd.DataFrame(dict(case=hist[col(hist, "識別番号")], term=hist[col(hist, "原疾患等")].astype(str)))
    return D, Rr, H


def build_pairs(D, Rr, H, mapper, levels):
    sus = D[D.role.astype(str).str.contains("被疑")].copy()
    sus["adc"] = sus.name.map(lambda n: next((a for a, ja in ADC_JA.items() if ja in n), None))
    per_case = sus.dropna(subset=["adc"]).groupby("case").adc.agg(lambda x: sorted(set(x)))
    cases = per_case[per_case.map(len) == 1].map(lambda x: x[0])                      # exactly one ADC as suspect
    Rr, H = Rr[Rr.case.isin(cases.index)], H[H.case.isin(cases.index)]
    m = mapper.map(list(Rr.term) + list(H.term))
    ae = Rr.assign(ax=Rr.term.map(m)).dropna(subset=["ax"]).groupby("case").ax.agg(set)
    hx = H.assign(ax=H.term.map(m)).dropna(subset=["ax"]).groupby("case").ax.agg(set)
    rows = []
    for case, adc in cases.items():
        a, h = ae.get(case, set()), hx.get(case, set())
        for o in AXES: rows.append((case, adc, o, int(o in a), int(o in h), levels[adc][o]))
    return pd.DataFrame(rows, columns=["case", "adc", "organ", "y", "v", "L"]), cases


def _auc(s, y):
    from matcher import auroc
    return auroc(np.asarray(s, float), np.asarray(y, bool))


def _or(sub):
    a = ((sub.L > 0) & (sub.y == 1)).sum() + .5; b = ((sub.L > 0) & (sub.y == 0)).sum() + .5
    c = ((sub.L == 0) & (sub.y == 1)).sum() + .5; d = ((sub.L == 0) & (sub.y == 0)).sum() + .5
    return a * d / (b * c)


def _logit_fit(X, y):
    from scipy.optimize import minimize
    nll = lambda w: np.sum(np.logaddexp(0, X @ w) - y * (X @ w)) + 1e-3 * np.sum(w[1:] ** 2)
    return minimize(nll, np.zeros(X.shape[1]), method="L-BFGS-B").x


def analyse(P, n_boot=1000, seed=0, k=5):
    rng = np.random.default_rng(seed); out = dict(n_cases=int(P.case.nunique()), n_pairs=len(P), events=int(P.y.sum()), vulnerable_pairs=int(P.v.sum()))
    V = P[P.v == 1]
    out["vulnerable_auroc_L"] = float(_auc(V.L, V.y)) if V.y.nunique() == 2 else None
    out["or_warned_vulnerable"], out["or_warned_not_vulnerable"] = float(_or(V)), float(_or(P[P.v == 0]))
    out["ratio_of_or"] = out["or_warned_vulnerable"] / out["or_warned_not_vulnerable"]
    # out-of-fold models, folds by case
    cs = P.case.unique(); fold = dict(zip(rng.permutation(cs), np.arange(len(cs)) % k)); f = P.case.map(fold).values
    Lb, Lw = (P.L == 2).astype(float).values, (P.L == 1).astype(float).values; v = P.v.astype(float).values; y = P.y.astype(float).values
    org = pd.get_dummies(P.organ).reindex(columns=AXES, fill_value=0).values.astype(float)           # organ base rates in both models
    X0 = np.c_[np.ones(len(P)), org[:, 1:], Lb, Lw]; X1 = np.c_[X0, v, v * Lb, v * Lw]
    p0, p1 = np.zeros(len(P)), np.zeros(len(P))
    for i in range(k):
        tr, te = f != i, f == i
        p0[te] = 1 / (1 + np.exp(-X0[te] @ _logit_fit(X0[tr], y[tr]))); p1[te] = 1 / (1 + np.exp(-X1[te] @ _logit_fit(X1[tr], y[tr])))
    out["oof_auroc_label_only"], out["oof_auroc_with_patient"] = float(_auc(p0, y)), float(_auc(p1, y))
    w_full = _logit_fit(X1, y); out["interaction_coef_boxed"], out["interaction_coef_warn"] = float(w_full[-2]), float(w_full[-1])
    z = np.log(np.clip(p1, 1e-6, 1 - 1e-6) / np.clip(1 - p1, 1e-6, 1)); w = _logit_fit(np.c_[np.ones(len(z)), z], y)
    from scipy.optimize import minimize
    citl = float(minimize(lambda a: np.sum(np.logaddexp(0, a + z) - y * (a + z)), [0.0]).x[0])
    out["calibration"] = dict(brier=float(np.mean((p1 - y) ** 2)), brier_base_rate=float(np.mean((y.mean() - y) ** 2)), in_the_large=citl, slope=float(w[1]))
    # bootstrap over cases
    by = {c: idx for c, idx in P.groupby("case").indices.items()}; bs = {k_: [] for k_ in ("vuln", "ror", "diff")}
    for _ in range(n_boot):
        j = np.concatenate([by[c] for c in rng.choice(cs, len(cs))]); Q = P.iloc[j]; Vq = Q[Q.v == 1]
        if Vq.y.nunique() == 2: bs["vuln"].append(_auc(Vq.L, Vq.y))
        bs["ror"].append(_or(Vq) / _or(Q[Q.v == 0]))
        if len(set(y[j])) == 2: bs["diff"].append(_auc(p1[j], y[j]) - _auc(p0[j], y[j]))
    ci = lambda x: [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))] if x else None
    out["vulnerable_auroc_L_ci"], out["ratio_of_or_ci"], out["patient_info_auroc_diff_ci"] = ci(bs["vuln"]), ci(bs["ror"]), ci(bs["diff"])
    out["patient_info_auroc_diff"] = out["oof_auroc_with_patient"] - out["oof_auroc_label_only"]
    from scipy.stats import spearmanr
    per = {}
    for o in AXES:
        S = V[V.organ == o]
        g = S.groupby("adc").agg(L=("L", "first"), share=("y", "mean"), n=("y", "size")); g = g[g.n >= 5]
        if len(g) >= 4 and g.L.nunique() > 1: r, p = spearmanr(g.L, g.share); per[o] = dict(spearman=float(r), p=float(p), n_adc=len(g), n_cases=int(g.n.sum()))
    out["per_organ_drug_order"] = per
    return out


def main(d):
    import drug_evidence as DE
    E = DE.evidence(); levels = {a: {o: {"boxed": 2, "W&P": 1}.get(E[a]["organs"][o]["level"], 0) for o in AXES} for a in E}
    D, Rr, H = read_jader(d); mapper = OrganMapper(); P, cases = build_pairs(D, Rr, H, mapper, levels)
    print(f"JADER at {d}: {len(cases)} cases with exactly one ADC as suspect drug; by ADC: {cases.value_counts().to_dict()}")
    terms = pd.concat([Rr[Rr.case.isin(cases.index)].term, H[H.case.isin(cases.index)].term]).value_counts()
    print("\nmost frequent terms and their organ (audit):")
    for t, n in terms.head(150).items(): print(f"   {n:6d}  {t:30s} {mapper.cache.get(t)!s:20s} {mapper.how.get(t)}")
    cov = sum(n for t, n in terms.items() if mapper.cache.get(t)) / terms.sum(); print(f"   term mentions mapped to an organ: {cov:.1%}")
    res = analyse(P); res.update(source=f"PMDA JADER ({os.path.basename(os.path.normpath(d))})", citation="本解析は医薬品医療機器総合機構（PMDA）の医薬品副作用データベース（JADER）を利用した結果である",
                                cases_by_adc=cases.value_counts().to_dict(), mapped_share=cov)
    json.dump(res, open(R + "ml/results/jader_validation.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_organ_drug_order", "cases_by_adc")}, indent=1, ensure_ascii=False))
    for o, x in res["per_organ_drug_order"].items(): print(f"   {o:20s} rho {x['spearman']:+.2f} (p {x['p']:.3f}, {x['n_adc']} ADCs, {x['n_cases']} vulnerable cases)")
    return res


if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(1)
    main(sys.argv[1])
