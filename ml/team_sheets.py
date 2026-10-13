"""Spreadsheets for teammates (fill cells only) and the import of the filled files into the training and evaluation formats.

    $PY -I ml/team_sheets.py make                         write the blank sheets to data/curated/team_sheets/
    $PY -I ml/team_sheets.py organs A.csv B.csv [C.csv]   organ review: two independent copies (+ a third for disagreements)
    $PY -I ml/team_sheets.py picks A.csv [B.csv]          right-candidate picks -> data/curated/train_queries/human_picks_*.jsonl
    $PY -I ml/team_sheets.py real-inputs F.csv            collected inputs -> queries_real_v1.json + the pick sheet for their gold
    $PY -I ml/team_sheets.py real-gold A.csv B.csv [C.csv] picked gold for real inputs -> gold_real_v1.jsonl
    $PY -I ml/team_sheets.py korean F.csv                 Korean expressions -> data/curated/korean/lay_aliases.tsv
    $PY -I ml/team_sheets.py abbrev F.csv                 abbreviations -> data/curated/abbreviations/team.tsv

Sheets are UTF-8 CSV with a BOM so Excel opens Korean text directly. Teammates mark organs with O and pick candidates by number;
columns marked (수정 금지) carry ids and must not be edited. Every import checks the values and prints the row numbers of
problems instead of guessing. Two reviewers' copies are compared: only agreeing rows (or rows a third reviewer settled) become
labels; disagreements are written to a new sheet of the same layout for the third reviewer.
"""
import csv, datetime, json, os, random, re, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adc_paths as P

CUR = Path(P.REPO) / "data/curated"; SHEETS = CUR / "team_sheets"
AXES = ["haematologic", "hepatic", "cardiovascular", "pulmonary", "renal", "gastrointestinal", "neurologic", "ocular", "dermatologic", "metabolic_endocrine", "musculoskeletal", "infectious_immune", "otologic"]
KO = ["혈액", "간", "심장혈관", "폐", "신장", "위장관", "신경", "눈", "피부", "대사내분비", "근골격", "감염면역", "귀"]
NONE, UNSURE = "해당 장기 없음", "모르겠음"
ORGAN_COLS = KO + [NONE, UNSURE]
TODAY = datetime.date.today().isoformat()


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print("wrote", path, len(rows), "rows")


def read(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f: rows = list(csv.DictReader(f))
    except UnicodeDecodeError:                                  # Excel's plain "CSV" save on a Korean Windows PC
        with open(path, newline="", encoding="cp949") as f: rows = list(csv.DictReader(f))
    return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in rows]


def marked(v): return v.strip().upper() in ("O", "0", "○", "●", "V", "X", "1", "Y", "YES", "예")


def organ_answer(r, line, errors):
    """-> ('axis', [axes]) / ('no_axis', []) / ('unclear', []) / None (row left empty)."""
    picked = [AXES[i] for i, k in enumerate(KO) if marked(r.get(k, ""))]
    none, unsure = marked(r.get(NONE, "")), marked(r.get(UNSURE, ""))
    if not picked and not none and not unsure: return None
    if (none or unsure) and picked or (none and unsure):
        errors.append(f"{line}행: 장기와 '{NONE}'/'{UNSURE}'를 함께 표시했습니다"); return None
    if len(picked) > 4: errors.append(f"{line}행: 장기는 최대 4개까지입니다 ({len(picked)}개)"); return None
    return ("unclear", []) if unsure else ("no_axis", []) if none else ("axis", picked)


def candidates(texts, k=6):
    """the linker's top distinct MONDO concepts for each text (SapBERT over the current index)."""
    import numpy as np, torch, mondo_index as MI
    MI.link(["asthma"]); E = MI._IDX_E; ids = MI._IDX["_ids"]; names = [str(x) for x in MI._IDX["names"]]
    pref = {}
    for t, n in zip(ids, names): pref.setdefault(t, n)
    out = []
    for i in range(0, len(texts), 256):
        Q = torch.from_numpy(MI._embed(texts[i:i + 256], "cuda:0" if torch.cuda.is_available() else "cpu").astype(np.float32)).to(E.device)
        with torch.no_grad(): v, j = (Q @ E.T).topk(64, dim=1)
        for row in j.cpu().numpy():
            seen = []
            for jj in row:
                if ids[jj] not in seen: seen.append(ids[jj])
                if len(seen) == k: break
            out.append([(t, pref[t]) for t in seen])
    return out


def pick_sheet(path, items, rng, extra_cols=()):
    """items: [(row id, typed text, [(id, name)])]. Candidate order is shuffled so position says nothing about the model."""
    header = ["번호", "입력"] + [f"후보{i}" for i in range(1, 7)] + ["정답 번호 (1-6, 없으면 0)", "정답이 없을 때 정답 질환 이름"] + list(extra_cols) + ["검토자", "메모"] + [f"후보{i} ID (수정 금지)" for i in range(1, 7)]
    rows = []
    for rid, text, cands in items:
        c = list(cands); rng.shuffle(c); c += [("", "")] * (6 - len(c))
        rows.append([rid, text] + [n for _, n in c] + ["", ""] + [""] * len(extra_cols) + ["", ""] + [t for t, _ in c])
    write(path, header, rows)


# ------------------------------------------------------------------ make the blank sheets
def make():
    from build_linking_pools import read_obo
    import linking_models as LM
    rng = random.Random(0); T = read_obo()
    # 1. organ review: concepts most mentioned in the literature, those where rule and model disagree first; gold-related left out
    queue = [r for r in csv.DictReader(open(CUR / "concept_organs/review_queue.csv", encoding="utf-8")) if r["use"] == "training"]
    queue.sort(key=lambda r: (-int(r["disagree"]), -int(r["mentions"])))
    rows = []
    for n, r in enumerate(queue[:400], 1):
        d = re.sub(r"\s+", " ", T.get(r["id"], {}).get("defn", "") or "")[:220]
        rows.append([n, r["name"], d] + [""] * len(ORGAN_COLS) + ["", "", r["id"]])
    write(SHEETS / "1_장기판정_검토.csv", ["번호", "질환 이름", "설명(참고)"] + ORGAN_COLS + ["검토자", "메모", "질환 ID (수정 금지)"], rows)
    # 2. right-candidate picks for typed inputs (abbreviations, typos, everyday words; generated inputs, gold concepts excluded)
    held = LM.gold_held(T); qs = []
    for k in range(5):
        for x in map(json.loads, open(CUR / f"train_queries/gen/gen_{k}.jsonl")):
            if x["category"] in ("abbrev", "typo", "lay") and x["concept"] not in held: qs.append(x)
    by = {c: [x for x in qs if x["category"] == c] for c in ("abbrev", "typo", "lay")}
    chosen = [x for c in by for x in rng.sample(by[c], 100)]; rng.shuffle(chosen)
    cands = candidates([x["query"] for x in chosen])
    pick_sheet(SHEETS / "2_정답후보_고르기.csv", [(f"p{n:03d}", x["query"], c) for n, (x, c) in enumerate(zip(chosen, cands), 1)], rng)
    # 3. collecting real inputs
    write(SHEETS / "3_실제입력_수집.csv", ["번호", "입력한 그대로", "뜻하는 질환 (정식 이름, 한글 가능)", "입력한 사람 직군 (선택)", "메모"],
          [[1, "당뇨", "제2형 당뇨병", "간호사", "예시입니다. 지우고 쓰세요"], [2, "ckd 3기", "만성 콩팥병 3기", "의사", "예시"]])
    # 4. Korean expressions, 5. abbreviations, 6. disease-pair data template
    write(SHEETS / "4_한국어_표현.csv", ["번호", "한국어 표현 (환자나 의료진이 실제로 쓰는 말)", "뜻하는 질환 영어 이름", "메모"],
          [[1, "중풍", "stroke", "예시"], [2, "간경화", "cirrhosis of liver", "예시"]])
    write(SHEETS / "5_약어.csv", ["번호", "약어", "뜻 (영어 전체 이름)", "주로 쓰는 분야 (선택)", "메모"],
          [[1, "CKD", "chronic kidney disease", "신장내과", "예시"], [2, "ILD", "interstitial lung disease", "호흡기내과", "예시"]])
    write(SHEETS / "6_질환쌍_양식.csv", ["exposure_code", "exposure_system", "exposure_name_en", "outcome_code", "outcome_system", "outcome_name_en",
                                       "effect_type", "effect", "ci_low", "ci_high", "p", "n_exposed", "n_cases", "lag_years", "selection", "cohort"],
          [["E11", "ICD10", "Type 2 diabetes mellitus", "N18", "ICD10", "Chronic kidney disease", "HR", "1.84", "1.71", "1.98", "1e-12", "52031", "1840", "0", "all_pairs", "예시"]])


# ------------------------------------------------------------------ imports
def organs(paths):
    errors, sheets = [], []
    for p in paths:
        rows = read(p); ans = {}
        for n, r in enumerate(rows, 2):
            if not r.get("질환 ID (수정 금지)", "").startswith("MONDO:"): errors.append(f"{p.name} {n}행: 질환 ID가 없거나 바뀌었습니다"); continue
            a = organ_answer(r, f"{p.name} {n}", errors)
            if a: ans[r["질환 ID (수정 금지)"]] = (a, r.get("검토자", ""), r)
        sheets.append(ans)
    if errors: print("\n".join(errors)); sys.exit("고친 뒤 다시 실행하세요. 아무것도 저장하지 않았습니다.")
    A, B = sheets[0], sheets[1]; C = sheets[2] if len(sheets) > 2 else {}
    out, conflicts = [], []
    for t in sorted(set(A) & set(B)):
        a, b = A[t][0], B[t][0]
        if a == b or t in C:
            final, who = (a, f"{A[t][1]}+{B[t][1]}") if a == b else (C[t][0], f"{A[t][1]}+{B[t][1]}+{C[t][1]}")
            if final[0] != "unclear": out.append(dict(id=t, organs=final[1], scope=final[0], confidence="high", reviewer=who, note=(C.get(t, (0, 0, {}))[2].get("메모", "") or "")))
        else:
            r = A[t][2]; conflicts.append([r["번호"], r["질환 이름"], r.get("설명(참고)", "")] + [""] * len(ORGAN_COLS) + ["", f"A: {', '.join(a[1]) or a[0]} / B: {', '.join(b[1]) or b[0]}", t])
    agree = sum(A[t][0] == B[t][0] for t in set(A) & set(B)) / max(1, len(set(A) & set(B)))
    dest = CUR / f"concept_organs/labels/expert_team_{TODAY}.jsonl"
    with open(dest, "w", encoding="utf-8") as f:
        for x in out: f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(f"both reviewed {len(set(A) & set(B))}, agreement {agree:.2f}, labels written {len(out)} -> {dest}")
    if conflicts:
        write(SHEETS / f"1_장기판정_불일치_{TODAY}.csv", ["번호", "질환 이름", "설명(참고)"] + ORGAN_COLS + ["검토자", "메모", "질환 ID (수정 금지)"], conflicts)
        print("disagreements go to the sheet above for a third reviewer; import it again as the third file")


def _picks(rows, name, errors):
    got = {}
    for n, r in enumerate(rows, 2):
        v = r.get("정답 번호 (1-6, 없으면 0)", "")
        if not v: continue
        if not re.fullmatch(r"[0-6]", v): errors.append(f"{name} {n}행: 정답 번호는 0~6 중 하나입니다 ('{v}')"); continue
        cid = r.get(f"후보{v} ID (수정 금지)", "") if v != "0" else ""
        if v != "0" and not cid: errors.append(f"{name} {n}행: {v}번 후보가 비어 있습니다"); continue
        got[r["번호"]] = (cid or None, r.get("정답이 없을 때 정답 질환 이름", ""), r)
    return got


def picks(paths):
    errors = []; sheets = [_picks(read(p), p.name, errors) for p in paths]
    if errors: print("\n".join(errors)); sys.exit("고친 뒤 다시 실행하세요. 아무것도 저장하지 않았습니다.")
    A = sheets[0]; B = sheets[1] if len(sheets) > 1 else None
    keep = [k for k in A if B is None or (k in B and B[k][0] == A[k][0])]
    dest = CUR / f"train_queries/human_picks_{TODAY}.jsonl"
    with open(dest, "w", encoding="utf-8") as f:
        for k in keep:
            cid, other, r = A[k]
            f.write(json.dumps(dict(query=r["입력"], concept=cid, none_name=other if cid is None else "", reviewer=r.get("검토자", ""), source="team_pick"), ensure_ascii=False) + "\n")
    print(f"picks kept {len(keep)} of {len(A)}" + (f" (two reviewers agree on {len(keep)}/{len(set(A) & set(B))})" if B else "") + f" -> {dest}")


def real_inputs(path):
    rows = [r for r in read(path) if r.get("입력한 그대로") and "예시" not in r.get("메모", "")]
    qs = [dict(qid=f"r{n:04d}", query=r["입력한 그대로"], intended=r.get("뜻하는 질환 (정식 이름, 한글 가능)", ""), category="", group="",
               lang="ko" if re.search("[가-힣]", r["입력한 그대로"]) else "en", source=f"team_{TODAY}", role=r.get("입력한 사람 직군 (선택)", "")) for n, r in enumerate(rows, 1)]
    dest = CUR / "disease_linking/raw/queries_real_v1.json"; dest.parent.mkdir(parents=True, exist_ok=True)
    json.dump(qs, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=1); print("wrote", dest, len(qs))
    import recommend as RC
    texts = RC.english([q["query"] for q in qs])                    # Korean inputs are searched by their English name, as the app does
    cands = candidates([f"{t}" for t in texts])
    extra = ["뜻이 여러 개라 정할 수 없음 (O)"] + ORGAN_COLS
    pick_sheet(SHEETS / "3b_실제입력_정답고르기.csv", [(q["qid"], f"{q['query']}  →  {q['intended']}" if q["intended"] else q["query"], c) for q, c in zip(qs, cands)],
               random.Random(1), extra_cols=extra)


def real_gold(paths):
    qs = {q["qid"]: q for q in json.load(open(CUR / "disease_linking/raw/queries_real_v1.json", encoding="utf-8"))}
    errors, sheets = [], []
    for p in paths:
        rows = read(p); got = _picks(rows, p.name, errors); ans = {}
        for n, r in enumerate(rows, 2):
            amb = marked(r.get("뜻이 여러 개라 정할 수 없음 (O)", ""))
            org = organ_answer(r, f"{p.name} {n}", errors)
            if r["번호"] in got or amb or org: ans[r["번호"]] = (got.get(r["번호"], (None, "", r))[0], amb, org)
        sheets.append(ans)
    if errors: print("\n".join(errors)); sys.exit("고친 뒤 다시 실행하세요. 아무것도 저장하지 않았습니다.")
    A, B = sheets[0], sheets[1]; C = sheets[2] if len(sheets) > 2 else {}
    def record(qid, a):
        cid, amb, org = a
        return dict(qid=qid, validity="ambiguous" if amb else "valid", concepts=[cid] if cid else [], best=cid, organs=org[1] if org else [], source="team", note="")
    out, conflicts = [], 0
    for qid in sorted(set(A) & set(B)):
        if A[qid] == B[qid]: out.append(record(qid, A[qid]))
        elif qid in C: out.append(record(qid, C[qid]))
        else: conflicts += 1
    dest = CUR / "disease_linking/gold_real_v1.jsonl"
    with open(dest, "w", encoding="utf-8") as f:
        for x in out: f.write(json.dumps(x, ensure_ascii=False) + "\n")
    for x in out:                                                   # group = the chosen concept, so inputs for one disease stay together
        qs[x["qid"]]["group"] = x["best"] or x["qid"]
    json.dump(list(qs.values()), open(CUR / "disease_linking/raw/queries_real_v1.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"gold written {len(out)}, unresolved disagreements {conflicts} (send the same sheet rows to a third reviewer) -> {dest}")


def korean(path):
    rows = [r for r in read(path) if "예시" not in r.get("메모", "")]
    dest = CUR / "korean/lay_aliases.tsv"; have = {l.split("\t")[0] for l in open(dest, encoding="utf-8") if "\t" in l and not l.startswith("#")}
    add = [(r["한국어 표현 (환자나 의료진이 실제로 쓰는 말)"], r["뜻하는 질환 영어 이름"]) for r in rows if r.get("한국어 표현 (환자나 의료진이 실제로 쓰는 말)") and r.get("뜻하는 질환 영어 이름")]
    add = [(k, e) for k, e in add if k not in have]
    with open(dest, "a", encoding="utf-8") as f:
        for k, e in add: f.write(f"{k}\t{e}\n")
    print(f"added {len(add)} Korean expressions -> {dest} (then: python -I ml/linking_models.py index3)")


def abbrev(path):
    rows = [r for r in read(path) if "예시" not in r.get("메모", "") and r.get("약어") and r.get("뜻 (영어 전체 이름)")]
    bad = [f"{n}행: '{r['약어']}'는 약어 형식(영문자로 시작, 2~6자)이 아닙니다" for n, r in enumerate(rows, 2) if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,5}", r["약어"])]
    if bad: print("\n".join(bad)); sys.exit("고친 뒤 다시 실행하세요.")
    dest = CUR / "abbreviations/team.tsv"; dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "a", encoding="utf-8") as f:
        for r in rows: f.write(f"{r['약어']}\t{r['뜻 (영어 전체 이름)']}\n")
    print(f"added {len(rows)} abbreviations -> {dest} (then: python -I ml/linking_models.py index2 and index3)")


if __name__ == "__main__":
    cmd, files = sys.argv[1], [Path(x) for x in sys.argv[2:]]
    {"make": lambda: make(), "organs": lambda: organs(files), "picks": lambda: picks(files), "real-inputs": lambda: real_inputs(files[0]),
     "real-gold": lambda: real_gold(files), "korean": lambda: korean(files[0]), "abbrev": lambda: abbrev(files[0])}[cmd]()
