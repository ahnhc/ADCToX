"""Public disease-mention corpora -> MONDO-linked mentions (training pairs and external evaluation for the linker).

    python -I ml/build_external_linking.py
      -> data/curated/external/ncbi_disease_mondo.jsonl   (NCBI Disease only; kept for the earlier scripts)
      -> data/curated/external/mentions_mondo.jsonl       (all corpora, one schema)

Sources, each keeps its own train / dev / test split:
  ncbi      NCBI Disease Corpus (Dogan et al. 2014), PubMed abstracts, MeSH/OMIM ids
  bc5cdr    BioCreative V CDR (Li et al. 2016), PubMed abstracts, Disease mentions with MeSH ids
  medmentions  MedMentions st21pv (Mohan & Li 2019), PubMed abstracts, UMLS CUIs
  cometa    COMETA (Basaldella et al. 2020), Reddit posts in everyday language, SNOMED CT ids (stratified_general split)
Concept ids are mapped to MONDO through the `xref:` lines of the MONDO snapshot (MESH, OMIM, UMLS, SCTID). Only mentions that
map to at least one MONDO concept are written to mentions_mondo.jsonl, which also drops the many non-disease MedMentions and
COMETA terms (drugs, procedures, symptoms without a MONDO equivalent). Several MONDO ids may share one xref; all are kept.
"""
import csv, gzip, json, os, re
from collections import Counter
RAW = "/home/hyeongchanahn/CONI/adctox/data/raw/"; OUT = "/home/hyeongchanahn/CONI/adctox/data/curated/external/"
OBO = "/home/hyeongchanahn/CONI/adctox/data/raw_big/mondo/2026-10-07/mondo.obo"


def xrefs():
    m, cur = {}, None
    for line in open(OBO, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == "[Term]": cur = None; continue
        if line.startswith("id: "): cur = line[4:].strip()
        elif line.startswith("xref: ") and cur and cur.startswith("MONDO:"):
            x = line[6:].split()[0]
            if x.startswith(("MESH:", "OMIM:", "UMLS:", "SCTID:")): m.setdefault(x, set()).add(cur)
    return m


def pubtator(path, split, source, X, keep_type=None, prefix=None):
    out = []
    opener = gzip.open if path.endswith(".gz") else open
    for line in opener(path, "rt", encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) != 6 or (keep_type and p[4] != keep_type): continue
        pmid, _, _, mention, typ, cid = p; mondo = set()
        for i in [i.strip() for i in re.split(r"[|+]", cid) if i.strip() and i.strip() != "-1"]:
            key = i if ":" in i else (prefix or ("MESH:" if i[0] in "DC" else "OMIM:")) + i
            mondo |= X.get(key, set())
        out.append(dict(source=source, split=split, doc=pmid, mention=mention, type=typ, source_ids=cid, mondo=sorted(mondo)))
    return out


def medmentions(X):
    d = RAW + "medmentions/"; split_of = {}
    for s, f in (("train", "pmids_trng.txt"), ("dev", "pmids_dev.txt"), ("test", "pmids_test.txt")):
        for l in open(d + f): split_of[l.strip()] = s
    out = []
    for r in pubtator(d + "st21pv_corpus_pubtator.txt.gz", "?", "medmentions", X, prefix="UMLS:"):
        r["split"] = split_of.get(r["doc"], "train"); out.append(r)
    return out


def cometa(X):
    d = RAW + "cometa/x/cometa/splits/stratified_general/"; out = []
    for s in ("train", "dev", "test"):
        if not os.path.exists(d + f"{s}.csv"): continue
        for row in csv.DictReader(open(d + f"{s}.csv", encoding="utf-8"), delimiter="\t"):
            sid = row.get("General SNOMED ID", "").strip(); mondo = sorted(X.get("SCTID:" + sid, set()))
            out.append(dict(source="cometa", split=s, doc=row.get("ID"), mention=row.get("Term", ""), type="layman", source_ids=sid, mondo=mondo))
    return out


def main():
    X = xrefs(); rows = []
    nc = RAW + "ncbi_disease/"
    ncbi = []
    for split, f in (("train", "NCBItrainset_corpus.txt"), ("develop", "NCBIdevelopset_corpus.txt"), ("test", "NCBItestset_corpus.txt")):
        ncbi += pubtator(nc + f, split, "ncbi", X)
    os.makedirs(OUT, exist_ok=True)
    with open(OUT + "ncbi_disease_mondo.jsonl", "w") as fh:                       # the earlier per-corpus file, unchanged schema
        for r in ncbi: fh.write(json.dumps(dict(split=r["split"], pmid=r["doc"], mention=r["mention"], type=r["type"], source_ids=r["source_ids"].split("|"), mondo=r["mondo"])) + "\n")
    rows += [dict(r, split={"develop": "dev"}.get(r["split"], r["split"])) for r in ncbi]
    cd = RAW + "bc5cdr/x/CDR_Data/CDR.Corpus.v010516/"
    for split, f in (("train", "CDR_TrainingSet.PubTator.txt"), ("dev", "CDR_DevelopmentSet.PubTator.txt"), ("test", "CDR_TestSet.PubTator.txt")):
        if os.path.exists(cd + f): rows += pubtator(cd + f, split, "bc5cdr", X, keep_type="Disease")
    if os.path.exists(RAW + "medmentions/st21pv_corpus_pubtator.txt.gz"): rows += medmentions(X)
    rows += cometa(X)
    kept = [r for r in rows if r["mondo"]]
    with open(OUT + "mentions_mondo.jsonl", "w") as fh:
        for r in kept: fh.write(json.dumps(r) + "\n")
    c = Counter((r["source"], r["split"]) for r in kept); a = Counter(r["source"] for r in rows)
    print("all mentions", dict(a)); print("mapped to MONDO", dict(c))
    print("unique mapped strings per source", {s: len({r["mention"].lower() for r in kept if r["source"] == s}) for s in a})


if __name__ == "__main__":
    main()
