"""PubMed abstracts for the from-scratch pretraining corpus (ml/scratch_pretrain.py --pubmed).

    python ml/fetch_pubmed.py [--n 300] [--out /data/hyeongchanahn/adctox/raw/pubmed]
    -> <out>/xml/pubmed26nNNNN.xml.gz (NCBI baseline, MD5-checked), <out>/text/pubmed26nNNNN.txt (one "title. abstract" per line),
       <out>/manifest.json

Source: the NLM PubMed annual baseline, https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/ (NLM terms: free to download and use;
abstracts may carry their publishers' copyright, so the files stay local and are never committed). Takes the last --n files of
the baseline (the most recent citations). Citations without an abstract are skipped.
"""
import argparse, glob, gzip, hashlib, json, os, re, subprocess, time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

BASE = "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/"


def listing():
    html = subprocess.run(["curl", "-s", "-m", "60", BASE], capture_output=True, text=True).stdout
    return sorted(set(re.findall(r"pubmed\d+n\d+\.xml\.gz(?=\")", html)))


def fetch(name, d):
    x = f"{d}/xml/{name}"; t = f"{d}/text/{name[:-7]}.txt"
    if os.path.exists(t): return name, "kept"
    for _ in range(5):
        md5 = subprocess.run(["curl", "-s", "-m", "60", BASE + name + ".md5"], capture_output=True, text=True).stdout.split()[-1]
        subprocess.run(["curl", "-s", "-m", "900", "-o", x, BASE + name], check=False)
        if os.path.exists(x) and hashlib.md5(open(x, "rb").read()).hexdigest() == md5: break
        time.sleep(10)
    else: return name, "failed"
    n = 0
    with gzip.open(x) as f, open(t + ".part", "w", encoding="utf-8") as o:
        for _, el in ET.iterparse(f):
            if el.tag != "PubmedArticle": continue
            title = "".join(el.find(".//ArticleTitle").itertext()) if el.find(".//ArticleTitle") is not None else ""
            ab = " ".join("".join(a.itertext()) for a in el.findall(".//Abstract/AbstractText"))
            if ab.strip(): o.write(re.sub(r"\s+", " ", f"{title} {ab}").strip() + "\n"); n += 1
            el.clear()
    os.rename(t + ".part", t); return name, n


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=300); ap.add_argument("--out", default="/data/hyeongchanahn/adctox/raw/pubmed")
    a = ap.parse_args(); os.makedirs(a.out + "/xml", exist_ok=True); os.makedirs(a.out + "/text", exist_ok=True)
    names = listing()[-a.n:]; print(len(names), names[0], names[-1], flush=True); res = {}
    with ThreadPoolExecutor(4) as ex:
        for name, r in ex.map(lambda n: fetch(n, a.out), names): res[name] = r; print(name, r, flush=True)
    files = sorted(glob.glob(a.out + "/text/*.txt"))
    man = dict(source=BASE, files=names, abstracts=sum(sum(1 for _ in open(f, encoding="utf-8")) for f in files), failed=[k for k, v in res.items() if v == "failed"],
               fetched=time.strftime("%Y-%m-%d %H:%M"))
    json.dump(man, open(a.out + "/manifest.json", "w"), indent=1); print(json.dumps({k: v for k, v in man.items() if k != "files"}, indent=1))
    if not man["failed"]: open(a.out + "/.done", "w").close()


if __name__ == "__main__":
    main()
