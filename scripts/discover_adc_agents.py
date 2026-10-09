"""Find every ADC that has published, by searching PMC for payload-linker name stems.

The corpus expansion needs agents, not arms: design features are agent-level constants, so
the 16 agents in the model put 224 identifying cells behind every design claim no matter
how many arms each one contributes. The plan puts the ceiling at about 54 agents -- the
ones that have published a per-organ safety table with a denominator -- against 370-plus
that have entered the clinic.

Discovery has to be unbiased, and the obvious method is not. Harvesting ADC names out of
the corpus already on disk found 18 non-registry agents, but that corpus was fetched by
searching for the 18 registry agents, so it only sees another ADC when a paper mentions it
alongside one of those. Six of the 18 were misspellings of registry agents.

The unbiased handle is the naming convention. An ADC's international nonproprietary name is
two words: an antibody stem, then a payload-linker stem coined for the conjugate class.
The payload-linker stems are a closed vocabulary -- `vedotin` is MMAE on a cleavable
dipeptide, `deruxtecan` is DXd on a GGFG tetrapeptide, `tesirine` is a PBD dimer, and so on
-- so searching each stem finds every agent built on that chemistry, including ones nobody
has written a review about. Any "<antibody stem> <payload stem>" pair in a returned title is
an ADC name whether or not it was in anyone's list.

This only reports names and counts. Design features have to be curated by hand into
`conf/adc_registry.yaml`, because the model's claims rest on them and a wrong payload family
would propagate into a mechanism coefficient.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from adctox.provenance import stamp  # noqa: E402

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
DELAY = 0.4          # NCBI asks for no more than 3 requests a second without a key
ESUMMARY_CHUNK = 200

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "adc_registry.yaml"

# Payload-linker stems. Each is the second word of at least one ADC INN, and each names a
# payload-and-linker chemistry rather than a target -- which is why the list is closed
# enough to search exhaustively and why a hit identifies an ADC rather than a bare antibody.
PAYLOAD_STEMS = (
    # Auristatins
    "vedotin", "mafodotin", "amadotin", "ledadotin", "pelidotin", "duostatin",
    # Maytansinoids
    "emtansine", "ravtansine", "soravtansine", "mertansine", "botansine",
    # Camptothecins and other topoisomerase-I payloads
    "deruxtecan", "govitecan", "tirumotecan", "rezetecan", "brengitecan", "sesutecan",
    "samrotecan", "adizutecan", "quilimotecan", "lezutecan", "cabotecan", "tafolecan",
    "vicotecan", "trimotecan", "iretecan", "exatecan",
    # DNA binders
    "tesirine", "talirine", "duocarmazine", "ozogamicin", "nogamicin", "arihecan",
    # Everything else
    "pasudotox", "sudotox", "sunirine", "ecteribulin", "rilsodotin", "clezutoclax",
    "sarotalocan", "doxorubicin", "paclitaxel", "zotiramab",
)

# An antibody stem followed by a payload stem. The antibody stems are the WHO suffixes,
# including the -tamab/-tumab forms the newer bispecifics use.
NAME = re.compile(
    r"\b([A-Za-z]{4,}(?:zumab|ximab|tumab|tamab|mumab|limab|nimab|cimab|mab))"
    r"[\s‐‑‒–-]+(" + "|".join(PAYLOAD_STEMS) + r")\b",
    re.I,
)


def _get(url: str, tries: int = 4) -> str | None:
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            time.sleep(DELAY * (2 ** attempt))
    return None


def esearch(term: str, retmax: int) -> list[str]:
    url = EUTILS + "esearch.fcgi?" + urllib.parse.urlencode({
        "db": "pmc", "term": term, "retmax": retmax, "retmode": "json",
    })
    time.sleep(DELAY)
    raw = _get(url)
    if raw is None:
        return []
    try:
        return json.loads(raw)["esearchresult"].get("idlist", [])
    except (KeyError, json.JSONDecodeError):
        return []


def esummary_titles(pmcids: list[str]) -> dict[str, str]:
    """Titles in bulk. One call per 200 ids, which is what makes this affordable."""
    out: dict[str, str] = {}
    for i in range(0, len(pmcids), ESUMMARY_CHUNK):
        chunk = pmcids[i:i + ESUMMARY_CHUNK]
        url = EUTILS + "esummary.fcgi?" + urllib.parse.urlencode({
            "db": "pmc", "id": ",".join(chunk), "retmode": "json",
        })
        time.sleep(DELAY)
        raw = _get(url)
        if raw is None:
            continue
        try:
            doc = json.loads(raw).get("result", {})
        except json.JSONDecodeError:
            continue
        for pmcid in chunk:
            rec = doc.get(pmcid)
            if isinstance(rec, dict) and rec.get("title"):
                out[pmcid] = str(rec["title"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--retmax", type=int, default=300,
                    help="PMCIDs per stem. The point is to see which names exist, not to "
                         "count their literature, so a cap well below the hit count is "
                         "fine as long as it is recorded.")
    ap.add_argument("--stems", default=None,
                    help="comma-separated subset, for a bounded trial run")
    args = ap.parse_args()

    stems = (
        [s.strip() for s in args.stems.split(",") if s.strip()]
        if args.stems else list(PAYLOAD_STEMS)
    )
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["agents"]
    known = {str(v["inn"]).lower() for v in registry.values() if v.get("inn")}

    found: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    titles_seen: dict[str, set[str]] = collections.defaultdict(set)
    per_stem: dict[str, dict] = {}

    for stem in stems:
        term = f'"{stem}"[Title/Abstract] AND open access[filter]'
        ids = esearch(term, args.retmax)
        titles = esummary_titles(ids) if ids else {}
        names: collections.Counter = collections.Counter()
        for pmcid, title in titles.items():
            for m in NAME.finditer(title):
                name = f"{m.group(1).lower()} {m.group(2).lower()}"
                names[name] += 1
                found[name][stem] += 1
                titles_seen[name].add(pmcid)
        per_stem[stem] = {
            "hits": len(ids), "titles_read": len(titles),
            "truncated": len(ids) >= args.retmax,
            "names": dict(names),
        }
        print(f"  {stem:16s} hits {len(ids):4d}  titles {len(titles):4d}  "
              f"names {len(names):3d}", flush=True)

    new = {n: titles_seen[n] for n in found if n not in known}
    print(f"\nINN 형태 {len(found)}종 발견 — 레지스트리 밖 {len(new)}종")
    print(f"  {'INN':42s} {'제목 수':>7s}  payload stem")
    for name, pmcids in sorted(new.items(), key=lambda kv: -len(kv[1])):
        stem = max(found[name], key=lambda s: found[name][s])
        print(f"  {name:42s} {len(pmcids):7d}  {stem}")

    truncated = [s for s, d in per_stem.items() if d["truncated"]]
    if truncated:
        print(f"\n주의: retmax {args.retmax}에 걸린 어간 {len(truncated)}개 "
              f"({', '.join(truncated[:8])}) — 이 어간의 희귀 약물은 누락될 수 있습니다")

    out = {
        "provenance": stamp({"registry": REGISTRY}),
        "source": EUTILS,
        "retmax": args.retmax,
        "stems_searched": stems,
        "per_stem": per_stem,
        "known_in_registry": sorted(known),
        "discovered": {
            name: {
                "n_titles": len(pmcids),
                "pmcids": sorted(pmcids)[:40],
                "stems": dict(found[name]),
                "in_registry": name in known,
            }
            for name, pmcids in sorted(
                titles_seen.items(), key=lambda kv: -len(kv[1])
            )
        },
        "n_discovered": len(found),
        "n_new": len(new),
        "truncated_stems": truncated,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
