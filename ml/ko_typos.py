"""Rule-based Korean typos (D3 in ml/docs/data_inventory.md): misspellings of the reviewed Korean MONDO names, made by changing
jamo the way Korean typists do. No language model; the same seed gives the same file.

    ADC_RESEARCH_MODE=1 python ml/ko_typos.py        # -> data/curated/judge2/gen/kotypo_NN.jsonl, kotypo_report.json

Why: Korean typos score lowest of all question types (dev F1 0.667 vs English 0.893, S1). A Korean typo changes jamo inside a
syllable, so the token changes completely; the model needs many examples, and only 2,133 concepts had any (ko2, gen_ko).

Names: korean/mondo_ko.jsonl (conf medium or high), the name and its alternatives, for labelled concepts that are not gold
concepts or their relatives (linking_models.gold_held). TYPOS_PER_NAME typos per name, each one edit (two for names longer than
LONG syllables), drawn from these rules with these weights:
  vowel     a confusable vowel (ㅔ/ㅐ, ㅗ/ㅓ, ㅜ/ㅡ, ㅕ/ㅑ, ㅚ/ㅙ/ㅞ, ㅢ/ㅣ, ㅘ/ㅏ, ㅝ/ㅓ)
  key       a jamo replaced by a neighbouring key of the 2-beolsik layout
  final     a final consonant dropped, added (ㅇ, ㄴ, ㅁ, ㄹ) or swapped (ㅇ/ㄴ/ㅁ, ㄱ/ㅋ, ㅂ/ㅍ, ㅅ/ㅆ)
  tense     plain / tense initial (ㄱ/ㄲ, ㄷ/ㄸ, ㅂ/ㅃ, ㅅ/ㅆ, ㅈ/ㅉ): the shift key
  stray     a stray jamo after the last syllable (ㅇ, ㅁ, ㄴ, ㅣ): the enter key missed
  swap      two neighbouring syllables swapped
  space     a space removed or inserted
Kept only when the result differs from every Korean name, alternative, KCD name and generated expression of any concept (so a
typo never spells another disease), has at least two Hangul syllables, and is not a duplicate.
"""
import collections, glob, json, os, random, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

SEED, TYPOS_PER_NAME, LONG, PER_FILE = 2051, 1, 6, 10000
W = dict(vowel=3, key=3, final=3, tense=1, stray=1, swap=1, space=1)
CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"; JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
VOWEL = [("ㅔ", "ㅐ"), ("ㅗ", "ㅓ"), ("ㅜ", "ㅡ"), ("ㅕ", "ㅑ"), ("ㅚ", "ㅙ"), ("ㅚ", "ㅞ"), ("ㅙ", "ㅞ"), ("ㅢ", "ㅣ"), ("ㅘ", "ㅏ"), ("ㅝ", "ㅓ"), ("ㅖ", "ㅔ")]
ROWS = ["ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ", "ㅁㄴㅇㄹㅎㅗㅓㅏㅣ", "ㅋㅌㅊㅍㅠㅜㅡ"]                    # 2-beolsik, unshifted
FINAL_SWAP = [("ㅇ", "ㄴ"), ("ㅇ", "ㅁ"), ("ㄴ", "ㅁ"), ("ㄱ", "ㅋ"), ("ㅂ", "ㅍ"), ("ㅅ", "ㅆ")]
TENSE = [("ㄱ", "ㄲ"), ("ㄷ", "ㄸ"), ("ㅂ", "ㅃ"), ("ㅅ", "ㅆ"), ("ㅈ", "ㅉ")]


def split(c):
    k = ord(c) - 0xAC00
    return (CHO[k // 588], JUNG[(k % 588) // 28], JONG[k % 28]) if 0 <= k < 11172 else None


def join(a, b, c): return chr(0xAC00 + CHO.index(a) * 588 + JUNG.index(b) * 28 + JONG.index(c))


def pairs(table, x): return [b for a, b in table if a == x] + [a for a, b in table if b == x]


def neighbours(j):
    out = []
    for r, row in enumerate(ROWS):
        if j in row:
            i = row.index(j); out += [row[k] for k in (i - 1, i + 1) if 0 <= k < len(row)]
            for rr in (r - 1, r + 1):
                if 0 <= rr < len(ROWS): out += [ROWS[rr][k] for k in (i - 1, i, i + 1) if 0 <= k < len(ROWS[rr])]
    return out


def edit(s, rng):
    """one typo of s by a rule drawn with weights W, or None when that rule does not apply."""
    rule = rng.choices(list(W), weights=list(W.values()))[0]; hs = [i for i, c in enumerate(s) if split(c)]
    if not hs: return None
    i = rng.choice(hs); a, b, c = split(s[i])
    put = lambda x: s[:i] + x + s[i + 1:]
    if rule == "vowel":
        o = pairs(VOWEL, b); return put(join(a, rng.choice(o), c)) if o else None
    if rule == "key":
        part = rng.choice([0, 1] + ([2] if c else []))
        if part == 0:
            o = [x for x in neighbours(a) if x in CHO]; return put(join(rng.choice(o), b, c)) if o else None
        if part == 1:
            o = [x for x in neighbours(b) if x in JUNG]; return put(join(a, rng.choice(o), c)) if o else None
        o = [x for x in neighbours(c) if x in JONG]; return put(join(a, b, rng.choice(o))) if o else None
    if rule == "final":
        if c and rng.random() < 0.5: return put(join(a, b, ""))
        if c:
            o = pairs(FINAL_SWAP, c); return put(join(a, b, rng.choice(o))) if o else None
        return put(join(a, b, rng.choice(["ㅇ", "ㄴ", "ㅁ", "ㄹ"])))
    if rule == "tense":
        o = pairs(TENSE, a); return put(join(rng.choice(o), b, c)) if o else None
    if rule == "stray": return s + rng.choice(["ㅇ", "ㅁ", "ㄴ", "ㅣ"])
    if rule == "swap":
        j = [k for k in hs if k + 1 < len(s) and split(s[k + 1])]
        if not j: return None
        k = rng.choice(j); return s[:k] + s[k + 1] + s[k] + s[k + 2:]
    if rule == "space":
        if " " in s and rng.random() < 0.7:
            k = rng.choice([k for k, ch in enumerate(s) if ch == " "]); return s[:k] + s[k + 1:]
        j = [k for k in range(1, len(s)) if split(s[k - 1]) and split(s[k])]
        if not j: return None
        k = rng.choice(j); return s[:k] + " " + s[k:]


def typo(s, rng, tries=20):
    n = 2 if sum(bool(split(c)) for c in s) > LONG else 1
    for _ in range(tries):
        t = s
        for _ in range(n):
            u = edit(t, rng); t = u if u else t
        if t != s: return t
    return None


def main():
    import linking_models as LM, tuning_ledger as TL
    from build_linking_pools import read_obo
    T = read_obo(); held = LM.gold_held(T); labels, _ = LM.load_organ_labels(); rng = random.Random(SEED)
    mk = [x for x in map(json.loads, open(P.REPO + "data/curated/korean/mondo_ko.jsonl", encoding="utf-8")) if x["conf"] != "low"]
    taken = {TL.norm(n) for x in mk for n in [x["ko"]] + x["alt"]}                        # every real name: a typo must not spell one
    Z = np.load(os.path.join(P.CACHE, "mondo_index.npz"), allow_pickle=True); taken |= {TL.norm(str(k)) for k in Z["ko_keys"]}
    for f in glob.glob(P.REPO + "data/curated/judge2/gen/ko*_*.jsonl"):
        if "kotypo" in f or "koeval" in f: continue
        for l in open(f, encoding="utf-8"):
            try: taken.add(TL.norm(json.loads(l).get("text", "")))
            except ValueError: pass
    out, seen, rules = [], set(), collections.Counter()
    for x in mk:
        t = x["id"]
        if t in held or t not in labels or t not in T: continue
        for name in [x["ko"]] + x["alt"]:
            if sum(bool(split(c)) for c in name) < 2: continue
            for _ in range(TYPOS_PER_NAME):
                y = typo(name, rng)
                if not y or TL.norm(y) in taken or (t, y) in seen or sum(bool(split(c)) for c in y) < 2: continue
                seen.add((t, y)); out.append(dict(id=t, text=y, kind="typo", of=name))
    for f in glob.glob(P.REPO + "data/curated/judge2/gen/kotypo_*.jsonl"): os.remove(f)
    for k in range(0, len(out), PER_FILE):
        open(P.REPO + f"data/curated/judge2/gen/kotypo_{k // PER_FILE:02d}.jsonl", "w", encoding="utf-8").write(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out[k:k + PER_FILE]))
    stats = dict(names=sum(1 + len(x["alt"]) for x in mk if x["id"] not in held and x["id"] in labels), typos=len(out),
                 concepts=len({r["id"] for r in out}), seed=SEED, weights=W, examples=[(r["of"], r["text"]) for r in out[:: max(1, len(out) // 30)]][:30])
    json.dump(stats, open(P.REPO + "data/curated/judge2/gen/kotypo_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
