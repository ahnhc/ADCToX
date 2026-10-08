#!/usr/bin/env python
"""Fetch per-organ expression for every ADC target antigen from Open Targets.

Why: constraint C3 asks whether a design's target is abundant in an organ the patient
cannot afford to lose -- the on-target off-tumour mechanism. It needs per-organ target
expression, which this repository did not ingest, so C3 was declared and never evaluated
and the target antigen changed nothing in the output. Measured before this script existed:
swapping ERBB2 for CD33 or for an invented name left the candidate list, the constraint
pass count, every organ estimate and every score bit-identical.

Open Targets serves four sources under one field and they must not be pooled -- TPM,
CPM-pseudobulk and mass-spectrometry PPB differ by orders of magnitude, and during the
survey a pituitary proteomics row at 13,265 outranked every RNA row. Two are kept:

  gtex            bulk RNA, TPM, 51 tissues. Has brain. No eye, no ear.
  tabula_sapiens  scRNA pseudobulk, CPM, 65 tissues, 170 cell types. Has eye and
                  vestibular ear. No brain.

Neither covers the 14 axes alone. Cell types are fetched because they decide whether a
cardiovascular flag is cardiomyocyte or an aortic smooth-muscle artefact, which is the
objection that made the project plan abandon this constraint.

Writes an immutable dated snapshot; the aggregation onto axes is a separate step so a
crosswalk change does not require re-fetching.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

API = "https://api.platform.opentargets.org/api/v4/graphql"
CONF = Path(__file__).resolve().parents[1] / "conf"

SEARCH = """query($q:String!){search(queryString:$q,entityNames:["target"],
 page:{index:0,size:10}){hits{id object{__typename ... on Target{approvedSymbol}}}}}"""

EXPR = """query($id:String!,$index:Int!,$size:Int!){target(ensemblId:$id){approvedSymbol
 baselineExpression(page:{index:$index,size:$size}){count rows{datasourceId datatypeId unit
 median min max tissueBiosampleFromSource celltypeBiosampleFromSource}}}}"""

# The API caps a page at 3000 rows, so a target with more is paged rather than truncated.
# A silent truncation here would drop whole organs from a target's profile and C3 would
# then pass a design on an organ it simply had not looked at.
PAGE_SIZE = 3000

KEEP = {"gtex", "tabula_sapiens"}


def _post(query: str, variables: dict, retries: int = 4) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                doc = json.loads(r.read())
            if "errors" in doc:
                raise RuntimeError(doc["errors"][0].get("message", "graphql error"))
            return doc
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last = exc
            # Backoff rather than hammering: a transient failure that silently became a
            # zero once wiped a whole agent out of this project's corpus.
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Open Targets failed after {retries} attempts: {last}")


def resolve(symbol: str) -> str:
    """Symbol -> Ensembl id, requiring an exact approvedSymbol match.

    Exactness matters: a fuzzy hit silently analyses the wrong gene, and the project has
    already measured Open Targets mis-resolving 3 of 36 disease terms to a different
    disease entirely.
    """
    hits = _post(SEARCH, {"q": symbol})["data"]["search"]["hits"]
    exact = [h for h in hits if (h.get("object") or {}).get("approvedSymbol") == symbol]
    if not exact:
        raise RuntimeError(
            f"no exact approvedSymbol match for {symbol!r}; "
            f"got {[ (h.get('object') or {}).get('approvedSymbol') for h in hits ]}"
        )
    return exact[0]["id"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--page-size", type=int, default=PAGE_SIZE)
    args = ap.parse_args()

    reg = yaml.safe_load(
        (CONF / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]
    # Every target in the registry, not only the conventional ADCs: the enumerator accepts
    # any target, and a target absent from this snapshot must report "not evaluated"
    # rather than pass C3 silently.
    targets = sorted({spec["target"] for spec in reg.values() if spec.get("target")})
    print(f"{len(targets)} target antigens from the registry")

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {"source": API, "targets": {}, "kept_datasources": sorted(KEEP)}
    for sym in targets:
        eid = resolve(sym)
        rows, total, index = [], None, 0
        while True:
            be = _post(
                EXPR, {"id": eid, "index": index, "size": args.page_size}
            )["data"]["target"]["baselineExpression"]
            total = be["count"] if total is None else total
            page = be["rows"] or []
            rows.extend(r for r in page if r["datasourceId"] in KEEP)
            fetched = (index + 1) * args.page_size
            if len(page) < args.page_size or fetched >= total:
                break
            index += 1
            time.sleep(0.3)
        seen = min(total, (index + 1) * args.page_size)
        if seen < total:
            raise RuntimeError(
                f"{sym}: paged {seen} of {total} rows; refusing to analyse a truncated "
                "expression profile"
            )
        be = {"count": total}
        per_src = {}
        for r in rows:
            per_src.setdefault(r["datasourceId"], []).append(r)
        (args.out / f"{sym}.json").write_text(
            json.dumps({"symbol": sym, "ensembl_id": eid, "rows": rows}, indent=1),
            encoding="utf-8",
        )
        manifest["targets"][sym] = {
            "ensembl_id": eid,
            "rows_total": be["count"],
            "rows_kept": len(rows),
            "by_source": {k: len(v) for k, v in sorted(per_src.items())},
        }
        missing = sorted(KEEP - set(per_src))
        flag = f"  <- {','.join(missing)} 없음" if missing else ""
        print(f"  {sym:10s} {eid}  kept {len(rows):5d} of {be['count']:5d}"
              f"  {manifest['targets'][sym]['by_source']}{flag}")
        time.sleep(0.4)

    (args.out / "_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
