#!/usr/bin/env python
"""Fetch each ADC label's dose-modification table from openFDA.

Why this is the strongest item in Module B per unit of work: every approved label's
section 2 contains a table keyed by adverse reaction and severity grade, saying whether to
monitor, reduce, withhold or permanently discontinue. That is the clinical community's
operational statement of which organs it fears for that drug, and it carries a built-in
severity ordering. The label-change analysis has 7 events; this has on the order of a
hundred ordered pairs across 14 drugs, and an ordinal outcome rather than a binary one.

One API note that costs a lot of coverage if missed: openFDA label lookups must search
`openfda.brand_name`. Searching `generic_name` returns only a minority of these products.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx
import yaml

API = "https://api.fda.gov/drug/label.json"
UA = {"User-Agent": "adctox-research/0.1 (dose-modification study)"}
CONF = Path(__file__).resolve().parents[1] / "conf"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--api-key", default=None,
                    help="openFDA key; without one the limit is 1,000 requests a day")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    doc = yaml.safe_load((CONF / "dailymed_setids.yaml").read_text(encoding="utf-8"))
    manifest: dict[str, dict] = {}

    with httpx.Client(follow_redirects=True) as client:
        for agent, spec in doc["agents"].items():
            brand = spec["brand"]
            params = {"search": f'openfda.brand_name:"{brand}"', "limit": 1}
            if args.api_key:
                params["api_key"] = args.api_key
            try:
                r = client.get(API, params=params, headers=UA, timeout=60)
            except httpx.HTTPError as exc:
                print(f"  ! {agent}: {exc}")
                manifest[agent] = {"brand": brand, "error": str(exc)}
                continue
            if r.status_code != 200:
                print(f"  ! {agent} ({brand}): HTTP {r.status_code}")
                manifest[agent] = {"brand": brand, "error": f"http_{r.status_code}"}
                continue
            results = r.json().get("results") or []
            if not results:
                print(f"  ! {agent} ({brand}): no label returned")
                manifest[agent] = {"brand": brand, "error": "no_results"}
                continue
            label = results[0]
            (args.out / f"{agent}.json").write_text(
                json.dumps(label, ensure_ascii=False), encoding="utf-8"
            )
            have = {
                k: bool(label.get(k))
                for k in (
                    "dosage_and_administration_table",
                    "dosage_and_administration",
                    "warnings_and_cautions",
                    "boxed_warning",
                    "use_in_specific_populations",
                )
            }
            n_tables = len(label.get("dosage_and_administration_table") or [])
            manifest[agent] = {
                "brand": brand, "version": label.get("version"),
                "effective_time": label.get("effective_time"),
                "n_dose_mod_tables": n_tables, "sections": have,
            }
            print(f"  {agent:26s} {brand:10s} v{label.get('version')} "
                  f"{n_tables} dose-mod tables  "
                  f"{'hepatic/renal text' if have['use_in_specific_populations'] else 'no 8.6/8.7'}")
            time.sleep(0.3)

    (args.out / "_manifest.json").write_text(
        json.dumps({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "api": API, "agents": manifest}, indent=1),
        encoding="utf-8",
    )
    ok = sum(1 for m in manifest.values() if "error" not in m)
    with_tables = sum(1 for m in manifest.values() if m.get("n_dose_mod_tables"))
    print(f"\n{ok}/{len(manifest)} labels retrieved, {with_tables} with a dose-modification table")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
