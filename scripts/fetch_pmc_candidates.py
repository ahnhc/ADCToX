#!/usr/bin/env python
"""Discover and fetch PMC Open Access papers that may carry an ADC adverse-event table.

Why this exists: every measurement in this project points at the same blocker. With 16
agents a per-axis across-agent Spearman has a standard error near 0.28, so the one positive
signal found -- the across-agent organ ranking, p = 0.025 after removing reporting
conditions -- cannot be settled by more analysis. It needs more agents, and the only place
they exist with a denominator attached is the literature.

The funnel is deliberately staged so the expensive step runs last:

  1. esearch per INN, restricted to the Open Access subset
  2. fetch the small .json per PMCID -- title, licence, retraction status
  3. filter on those, which is where most candidates die
  4. fetch the JATS .xml only for survivors

Stage 3 is the one that matters. The project plan measured the trap: detecting an agent
loosely marks 52 of 54 as "has an extractable AE table", while requiring the drug in the
title and a primary-report signature leaves 13 -- a 75% false-positive rate, because the
rest are review articles carrying other drugs' tables. One misattribution contaminates
every row of an agent, so this script errs toward rejecting and records why.

Nothing is filtered silently. The manifest carries the count at each stage and the reason
for every rejection, because a funnel that reports only its output is indistinguishable
from one with a bug in the middle.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
S3 = "https://pmc-oa-opendata.s3.amazonaws.com"
CONF = Path(__file__).resolve().parents[1] / "conf"

# NCBI asks for <=3 requests/second without an API key. The S3 mirror is a separate
# service with no documented limit, but a transient failure there once silently zeroed a
# whole agent in this project's history, so both paths back off and retry.
NCBI_DELAY = 0.4
S3_DELAY = 0.1

# Versions to probe on the S3 mirror. Hardcoding `.1` was measured to miss papers --
# gemtuzumab's dropped out entirely -- because PMC reissues with a higher version.
VERSIONS = (1, 2, 3, 4)

# A review's title says what it reviews. These phrases in a title mean the paper is about
# a field, not a trial, whatever drug it names.
REVIEW_TITLE = re.compile(
    r"\b(review|meta-?analys|systematic|overview|landscape|perspective|"
    r"state of the art|advances in|current status|emerging|future (of|direction)|"
    r"narrative|scoping|umbrella|bibliometric|editorial|commentary|correspondence|"
    r"letter to the editor|erratum|corrigendum)\b",
    re.I,
)


def _get(url: str, retries: int = 4, timeout: int = 90) -> bytes | None:
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed after {retries} attempts: {url}: {last}")


def esearch(term: str, retmax: int) -> list[str]:
    q = urllib.parse.urlencode(
        {"db": "pmc", "term": term, "retmax": retmax, "retmode": "json"}
    )
    raw = _get(EUTILS + "esearch.fcgi?" + q)
    if raw is None:
        return []
    return json.loads(raw)["esearchresult"].get("idlist", [])


def meta(pmcid: str) -> tuple[dict, int] | tuple[None, None]:
    """The small .json for a PMCID, probing versions. Also the licence oracle."""
    for v in VERSIONS:
        raw = _get(f"{S3}/PMC{pmcid}.{v}/PMC{pmcid}.{v}.json", retries=2, timeout=45)
        time.sleep(S3_DELAY)
        if raw is None:
            continue
        try:
            return json.loads(raw), v
        except json.JSONDecodeError:
            continue
    return None, None


def aliases_for(spec: dict) -> list[str]:
    """Names that identify this agent in a title. Brand and INN, not bare antibody stems.

    `trastuzumab` alone matches three different ADCs plus the naked antibody, so only
    multi-word INNs, the brand, and explicit code-style aliases are used.
    """
    out = {spec["inn"].lower(), str(spec.get("brand", "")).lower()}
    for a in spec.get("aliases", []):
        a = a.lower().strip()
        if not a:
            continue
        # Reject single-token antibody stems that collide across agents.
        if " " not in a and not re.search(r"[\d-]", a) and len(a) > 6 and a.endswith("mab"):
            continue
        out.add(a)
    return sorted(x for x in out if len(x) >= 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--retmax", type=int, default=400)
    ap.add_argument("--agents", nargs="*", default=None,
                    help="registry keys; default is every agent with an INN")
    ap.add_argument("--inns", default=None,
                    help="comma-separated INNs to fetch instead of registry agents, for "
                         "a discovery pass. Lets the yield be measured before any design "
                         "features are curated -- there is no point hand-curating a "
                         "payload family for an agent whose papers turn out to carry no "
                         "usable table, and a wrong family propagates into a mechanism "
                         "coefficient. The INN is its own and only alias.")
    ap.add_argument("--abstract-only", action="store_true",
                    help="also keep papers naming the agent only in the abstract. The "
                         "title requirement was a proxy for attribution; the extractor "
                         "now attributes at the column level, so these are recoverable -- "
                         "but their yield and precision must be reported separately.")
    ap.add_argument("--limit-xml", type=int, default=None,
                    help="stop after this many XML downloads (for a bounded first pass)")
    args = ap.parse_args()

    if args.inns:
        # "INN" or "INN=CODE1|CODE2". A code name is accepted only when it was harvested
        # from a paper whose *title* already named the INN, so the paper itself verifies
        # the mapping -- the alternative is recalling it, and a wrong code name
        # misattributes every row of an agent, which is the 75% false-positive trap.
        reg = {}
        for spec in args.inns.split(","):
            spec = spec.strip()
            if not spec:
                continue
            inn, _, codes = spec.partition("=")
            inn = inn.strip()
            reg[inn.lower().replace(" ", "_")] = {
                "inn": inn,
                "aliases": [c.strip() for c in codes.split("|") if c.strip()],
            }
        n_coded = sum(1 for v in reg.values() if v["aliases"])
        print(f"discovery mode: {len(reg)} INNs ({n_coded} with code names), "
              "registry not consulted", flush=True)
    else:
        reg = yaml.safe_load(
            (CONF / "adc_registry.yaml").read_text(encoding="utf-8")
        )["agents"]
    agents = args.agents or sorted(reg)
    xml_dir = args.out / "xml"
    xml_dir.mkdir(parents=True, exist_ok=True)

    funnel = {k: 0 for k in (
        "esearch_hits", "unique_pmcids", "meta_fetched", "meta_missing",
        "not_open_access", "retracted", "review_title", "agent_not_in_title",
        "passed_title_filter", "abstract_only", "xml_fetched", "xml_missing",
    )}
    rejected: dict[str, list[str]] = {}
    records: dict[str, dict] = {}
    seen: set[str] = set()

    for key in agents:
        spec = reg.get(key)
        if not spec or not spec.get("inn"):
            continue
        names = aliases_for(spec)
        # Code names are searched alongside the INN, because an agent's earliest and
        # often only primary reports use the code name and never the INN -- which is how
        # ten agents came back with no usable table from an INN-only search.
        handles = [spec["inn"]] + [
            a for a in (spec.get("aliases") or []) if any(ch.isdigit() for ch in a)
        ]
        joined = " OR ".join(f'"{h}"[Title/Abstract]' for h in handles)
        term = f"({joined}) AND open access[filter]"
        ids = esearch(term, args.retmax)
        time.sleep(NCBI_DELAY)
        funnel["esearch_hits"] += len(ids)
        fresh = [i for i in ids if i not in seen]
        seen.update(fresh)
        funnel["unique_pmcids"] += len(fresh)
        kept = 0
        for pmcid in fresh:
            doc, version = meta(pmcid)
            if doc is None:
                funnel["meta_missing"] += 1
                continue
            funnel["meta_fetched"] += 1
            title = str(doc.get("title") or "")
            low = title.lower()
            if not doc.get("is_pmc_openaccess"):
                funnel["not_open_access"] += 1
                rejected.setdefault("not_open_access", []).append(pmcid)
                continue
            if doc.get("is_retracted"):
                funnel["retracted"] += 1
                rejected.setdefault("retracted", []).append(pmcid)
                continue
            if REVIEW_TITLE.search(title):
                funnel["review_title"] += 1
                rejected.setdefault("review_title", []).append(pmcid)
                continue
            in_title = any(n in low for n in names)
            if not in_title and not args.abstract_only:
                funnel["agent_not_in_title"] += 1
                rejected.setdefault("agent_not_in_title", []).append(pmcid)
                continue
            funnel["passed_title_filter" if in_title else "abstract_only"] += 1
            records[pmcid] = {
                "pmcid": pmcid, "version": version, "agent_hint": key,
                "title": title, "license_code": doc.get("license_code"),
                "pmid": doc.get("pmid"), "doi": doc.get("doi"),
                # Which gate let this paper through. The title gate is the plan's
                # high-precision path; the abstract-only path relies entirely on the
                # column-level attribution in extract/table_to_cells.py, and the two have
                # to be measured separately or the looser one launders the stricter one's
                # precision.
                "attribution_gate": "title" if in_title else "abstract_only",
            }
            kept += 1
        print(f"  {key:28s} esearch {len(ids):4d}  new {len(fresh):4d}  "
              f"title-filter kept {kept:3d}", flush=True)

    print(f"\ntitle filter kept {len(records)} of {funnel['unique_pmcids']} unique PMCIDs")
    todo = sorted(records)
    if args.limit_xml:
        todo = todo[: args.limit_xml]
        print(f"  fetching XML for the first {len(todo)} (bounded pass)")
    for i, pmcid in enumerate(todo, 1):
        rec = records[pmcid]
        dest = xml_dir / f"PMC{pmcid}.xml"
        if dest.exists():
            funnel["xml_fetched"] += 1
            continue
        raw = _get(f"{S3}/PMC{pmcid}.{rec['version']}/PMC{pmcid}.{rec['version']}.xml")
        time.sleep(S3_DELAY)
        if raw is None:
            funnel["xml_missing"] += 1
            rejected.setdefault("xml_missing", []).append(pmcid)
            continue
        dest.write_bytes(raw)
        funnel["xml_fetched"] += 1
        if i % 25 == 0:
            print(f"    xml {i}/{len(todo)}", flush=True)

    (args.out / "_manifest.json").write_text(
        json.dumps({
            "source_esearch": EUTILS, "source_fulltext": S3,
            "funnel": funnel,
            "rejected_counts": {k: len(v) for k, v in sorted(rejected.items())},
            "rejected_pmcids": {k: sorted(v)[:200] for k, v in sorted(rejected.items())},
            "records": records,
            "_note": (
                "The title filter is the strict one the project plan calls for. Loose "
                "agent detection marks 52 of 54 agents as having an extractable AE table "
                "while the strict filter leaves 13, a 75% false-positive rate, because "
                "the rest are reviews carrying other drugs' tables. One misattribution "
                "contaminates every row of an agent."
            ),
        }, indent=1),
        encoding="utf-8",
    )
    print("\nfunnel:")
    for k, v in funnel.items():
        print(f"  {k:24s} {v:6d}")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
