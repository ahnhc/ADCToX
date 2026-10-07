#!/usr/bin/env python
"""Fetch every historical version of each ADC's US label from DailyMed.

Why this exists: the project's other analyses measure *consistency* with warnings that
already existed at approval, which is agreement, not anticipation. A warning that FDA
added to a label years after approval is the only genuinely anticipatory target available
in the public record -- the organ was not flagged, then it was, on a known date. A model
fit only on data predating that date either ranked the organ highly or it did not.

openFDA cannot serve this: `drug/label.json` returns one record per product with only the
current version. DailyMed's `spls/{setid}/history.json` lists every version with its date,
and `drugInfo.cfm?setid=&version=` serves the historical text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx
import yaml

HISTORY = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{set_id}/history.json"
VERSION_HTML = (
    "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}&version={version}"
)
UA = {"User-Agent": "adctox-research/0.1 (label-change study)"}
CONF = Path(__file__).resolve().parents[1] / "conf"


def _get(client: httpx.Client, url: str, tries: int = 4) -> httpx.Response | None:
    for attempt in range(tries):
        try:
            r = client.get(url, headers=UA, timeout=90)
            if r.status_code == 200:
                return r
            # A transient non-200 that is retried silently would drop a whole label
            # version, so back off and try again rather than moving on.
            time.sleep(2.0 * (attempt + 1))
        except httpx.HTTPError:
            time.sleep(2.0 * (attempt + 1))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--agents", default=None, help="comma-separated subset")
    args = ap.parse_args()

    doc = yaml.safe_load((CONF / "dailymed_setids.yaml").read_text(encoding="utf-8"))
    agents = doc["agents"]
    if args.agents:
        wanted = {a.strip() for a in args.agents.split(",")}
        agents = {k: v for k, v in agents.items() if k in wanted}

    manifest: dict[str, dict] = {}
    for agent, spec in agents.items():
        set_id = spec["set_id"]
        adir = args.out / agent
        adir.mkdir(parents=True, exist_ok=True)

        hist = _get(httpx.Client(follow_redirects=True), HISTORY.format(set_id=set_id))
        if hist is None:
            print(f"  ! {agent}: history unavailable")
            manifest[agent] = {"set_id": set_id, "error": "history_unavailable"}
            continue
        hdoc = hist.json()
        (adir / "_history.json").write_text(
            json.dumps(hdoc, ensure_ascii=False), encoding="utf-8"
        )
        versions = (hdoc.get("data") or {}).get("history") or []
        print(f"  {agent:26s} {spec['brand']:10s} {len(versions)} versions", flush=True)

        fetched = []
        with httpx.Client(follow_redirects=True) as client:
            for v in versions:
                num = v.get("spl_version")
                date = v.get("published_date")
                if num is None:
                    continue
                path = adir / f"v{num}.html"
                if path.exists():
                    fetched.append({"version": num, "date": date, "cached": True})
                    continue
                r = _get(client, VERSION_HTML.format(set_id=set_id, version=num))
                if r is None:
                    print(f"      ! version {num} unavailable")
                    continue
                path.write_text(r.text, encoding="utf-8")
                fetched.append(
                    {
                        "version": num, "date": date, "bytes": len(r.text),
                        "sha256": hashlib.sha256(r.text.encode()).hexdigest()[:16],
                    }
                )
                time.sleep(0.4)  # be polite to a government service
        manifest[agent] = {
            "set_id": set_id, "brand": spec["brand"],
            "n_versions": len(versions), "n_fetched": len(fetched), "versions": fetched,
        }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "_manifest.json").write_text(
        json.dumps(
            {
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "dailymed",
                "agents": manifest,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    total = sum(m.get("n_fetched", 0) for m in manifest.values())
    print(f"\n{total} label versions across {len(manifest)} agents -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
