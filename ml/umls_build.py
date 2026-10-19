"""UMLS Metathesaurus -> training files for the from-scratch judge (ml/scratch_judge.py via ml/judge_data.py).

    ADC_RESEARCH_MODE=1 python ml/umls_build.py --meta data/raw/umls/2026AA/META [--srl 0] [--langs ENG,KOR]
    -> data/curated/external/umls/{pairs.jsonl, items.jsonl, manifest.json}   (git-ignored: UMLS content is licensed)

Needs a UMLS licence (UTS account). The release is never committed; neither is anything built from it. Anyone reproducing
the run downloads UMLS with their own licence and runs this script; without it the judge trains without UMLS and its run card
says so.

Reads MRCONSO.RRF (names), MRSTY.RRF (semantic types). Keeps:
  concepts  of the Disorders semantic group (DISO_TUIS), not obsolete
  names     in LANGS, not suppressible (SUPPRESS N), from sources of restriction level in SRL (0 by default: the sources usable
            under the basic licence; add 9 for SNOMED CT only where the licence covers it), at most MAXLEN characters
Gold isolation, as everywhere in the project:
  - a concept linked (MONDO xref UMLS:C...) to a gold concept or a relative (linking_models.gold_held) is dropped entirely;
  - so is a concept any of whose names equals a held concept's MONDO name or synonym (normalised), linked or not;
  - a name equal to an evaluation question (English or Korean, tuning_ledger.eval_concepts) is dropped.
Outputs:
  pairs.jsonl  {"a", "b", "cui", "mondo"}: each concept's preferred English name with up to PAIRS_PER other names (Korean ones
               with the preferred English name); mondo when the concept links to exactly one labelled MONDO concept
  items.jsonl  {"text", "mondo", "kind"}: names of concepts linked to exactly one labelled MONDO concept (organ labels come from
               MONDO, so they train the organ output); kind abbrev for TTY AB/ACR, else name
"""
import argparse, collections, hashlib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import adc_paths as P

OUT = P.REPO + "data/curated/external/umls/"
DISO_TUIS = {"T020", "T190", "T049", "T019", "T047", "T050", "T033", "T037", "T048", "T191", "T046", "T184"}   # UMLS semantic group DISO
PAIRS_PER, MAXLEN = 10, 80
ABBR_TTY = {"AB", "ACR"}


def mondo_xrefs(obo):
    """{CUI: {MONDO ids}} from the xref lines of mondo.obo."""
    x, cur = collections.defaultdict(set), None
    for line in open(obo, encoding="utf-8"):
        if line.startswith("id: "): cur = line[4:].strip()
        elif line.startswith("xref: UMLS:") and cur: x[line.split()[1][5:]].add(cur)
    return x


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--meta", required=True); ap.add_argument("--srl", default="0")
    ap.add_argument("--langs", default="ENG,KOR"); ap.add_argument("--out", default=OUT); ap.add_argument("--obo", default=None)
    a = ap.parse_args(argv); meta = a.meta.rstrip("/") + "/"; srl = set(a.srl.split(",")); langs = set(a.langs.split(","))
    import linking_models as LM, tuning_ledger as TL, build_linking_pools as BLP
    T = BLP.read_obo(); held = LM.gold_held(T); labels, _ = LM.load_organ_labels(); ev = TL.eval_concepts()
    held_names = {TL.norm(n) for t in held if t in T for n in [T[t]["name"]] + T[t]["syn"]}
    xref = mondo_xrefs(a.obo or BLP.OBO)
    diso = set()
    for l in open(meta + "MRSTY.RRF", encoding="utf-8"):
        f = l.split("|")
        if f[1] in DISO_TUIS: diso.add(f[0])
    names, n_rows = collections.defaultdict(list), collections.Counter()
    for l in open(meta + "MRCONSO.RRF", encoding="utf-8"):
        f = l.split("|"); cui, lat, ts, stt, ispref, sab, tty, s, srl_, sup = f[0], f[1], f[2], f[4], f[6], f[11], f[12], f[14], f[15], f[16]
        n_rows["rows"] += 1
        if cui not in diso or lat not in langs or sup != "N" or srl_ not in srl or not s or len(s) > MAXLEN: continue
        names[cui].append(dict(s=s, lat=lat, pref=(ts == "P" and stt == "PF" and ispref == "Y"), tty=tty, sab=sab))
    drop_held, drop_name, drop_eval = 0, 0, 0; pairs, items = [], []
    for cui, ns in names.items():
        ms = xref.get(cui, set())
        if ms & held: drop_held += 1; continue
        if any(TL.norm(n["s"]) in held_names for n in ns): drop_name += 1; continue
        keep = []
        for n in ns:
            if TL.norm(n["s"]) in ev: drop_eval += 1; continue
            keep.append(n)
        en = [n for n in keep if n["lat"] == "ENG"]
        if not en: continue
        pref = next((n["s"] for n in en if n["pref"]), en[0]["s"]); lab = [m for m in ms if m in labels]; mondo = lab[0] if len(lab) == 1 else None
        seen, k = {TL.norm(pref)}, 0
        for n in sorted(keep, key=lambda n: (n["lat"] != "KOR", n["tty"] not in ABBR_TTY, n["s"])):     # Korean and abbreviations first
            if TL.norm(n["s"]) in seen or k >= PAIRS_PER: continue
            seen.add(TL.norm(n["s"])); pairs.append(dict(a=pref, b=n["s"], cui=cui, mondo=mondo)); k += 1
        if mondo:
            for s in {n["s"]: n for n in keep}.values(): items.append(dict(text=s["s"], mondo=mondo, kind="abbrev" if s["tty"] in ABBR_TTY else "name"))
    os.makedirs(a.out, exist_ok=True)
    for name, rows in (("pairs", pairs), ("items", items)):
        open(a.out + f"{name}.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    man = dict(meta=os.path.realpath(meta), srl=sorted(srl), langs=sorted(langs), mrconso_rows=n_rows["rows"], disorder_concepts=len(diso),
               concepts_with_names=len(names), dropped_held_link=drop_held, dropped_held_name=drop_name, dropped_eval_names=drop_eval,
               pairs=len(pairs), items=len(items), items_concepts=len({r["mondo"] for r in items}),
               korean_pairs=sum(1 for r in pairs if re.search("[가-힣]", r["b"])), sha=dict(pairs=sha(a.out + "pairs.jsonl"), items=sha(a.out + "items.jsonl")))
    json.dump(man, open(a.out + "manifest.json", "w"), indent=1); print(json.dumps(man, indent=1)); return man


if __name__ == "__main__":
    main()
