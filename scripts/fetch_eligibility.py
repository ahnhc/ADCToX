#!/usr/bin/env python
"""Fetch eligibility text for the ADC cohort and an oncology control cohort.

The organ-concern signal is only interpretable against a base rate: every oncology
protocol carries bilirubin, creatinine and LVEF floors, so a raw frequency says nothing
about the drug. The control cohort is therefore not optional -- it is what turns the
measurement into an enrichment.

Controls are drawn from interventional oncology trials with drug interventions that
match none of the ADC aliases, so the two cohorts differ in the drug class rather than
in the disease area.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from adctox.extract.arm_resolver import Registry  # noqa: E402

API = "https://clinicaltrials.gov/api/v2/studies"
UA = {"User-Agent": "adctox-research/0.1 (organ-concern base-rate study)"}
FIELDS = (
    "NCTId,BriefTitle,OverallStatus,StartDate,Phase,EligibilityCriteria,"
    "InterventionName,InterventionOtherName,InterventionType,Condition,LeadSponsorName,"
    "LeadSponsorClass"
)


def _get(client: httpx.Client, params: dict, tries: int = 5) -> dict:
    for attempt in range(tries):
        try:
            r = client.get(API, params=params, headers=UA, timeout=60)
            if r.status_code == 200:
                return r.json()
            # Transient 4xx from the search backend is common; back off and retry rather
            # than dropping the page, which silently zeroed an agent in an earlier run.
            time.sleep(1.5 * (attempt + 1))
        except httpx.HTTPError:
            time.sleep(1.5 * (attempt + 1))
    return {}


def fetch_pages(client: httpx.Client, params: dict, cap: int, label: str) -> list[dict]:
    out: list[dict] = []
    token = None
    while len(out) < cap:
        p = dict(params, fields=FIELDS, pageSize=200)
        if token:
            p["pageToken"] = token
        doc = _get(client, p)
        studies = doc.get("studies") or []
        if not studies:
            break
        out.extend(studies)
        token = doc.get("nextPageToken")
        print(f"  {label}: {len(out):,}", end="\r", flush=True)
        if not token:
            break
    print(f"  {label}: {len(out):,}      ")
    return out[:cap]


def flatten(study: dict) -> dict:
    proto = study.get("protocolSection") or {}
    ident = proto.get("identificationModule") or {}
    status = proto.get("statusModule") or {}
    design = proto.get("designModule") or {}
    arms = proto.get("armsInterventionsModule") or {}
    spons = proto.get("sponsorCollaboratorsModule") or {}
    names: list[str] = []
    for iv in arms.get("interventions") or []:
        if iv.get("name"):
            names.append(iv["name"])
        names.extend(iv.get("otherNames") or [])
    phases = design.get("phases") or []
    return {
        "nct_id": ident.get("nctId"),
        "title": ident.get("briefTitle"),
        "status": status.get("overallStatus"),
        "start_date": (status.get("startDateStruct") or {}).get("date"),
        "phase": phases[0] if phases else None,
        "eligibility": (proto.get("eligibilityModule") or {}).get("eligibilityCriteria"),
        "interventions": names,
        "conditions": (proto.get("conditionsModule") or {}).get("conditions") or [],
        "sponsor": (spons.get("leadSponsor") or {}).get("name"),
        "sponsor_class": (spons.get("leadSponsor") or {}).get("class"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--control-cap", type=int, default=2500)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    registry = Registry.load()

    with httpx.Client(follow_redirects=True) as client:
        print("ADC cohort (one query per INN, unioned by NCT id)")
        adc: dict[str, dict] = {}
        for key, spec in registry.agents.items():
            got = fetch_pages(
                client,
                {"query.intr": spec["inn"]},
                cap=600,
                label=spec["inn"][:34],
            )
            for s in got:
                row = flatten(s)
                if not row["nct_id"]:
                    continue
                # Client-side attribution: the API's own search is fuzzy enough that a
                # query for one ADC returns trials of another.
                hits = registry.find_agents(*row["interventions"], row["title"])
                if not hits:
                    continue
                row["adc_agents"] = hits
                adc[row["nct_id"]] = row
        print(f"\nADC trials with a confirmed ADC intervention: {len(adc):,}")
        if len(adc) < 100:
            raise SystemExit(
                f"ADC cohort came back with only {len(adc)} trials. Refusing to write a "
                "cohort this small: an empty or near-empty result here is far more "
                "likely to be a query fault than a fact about the literature. "
                "(An empty filter value returns HTTP 200 with zero studies.)"
            )

        print("\nOncology control cohort")
        controls: dict[str, dict] = {}
        for term in ("neoplasms", "carcinoma", "lymphoma", "leukemia", "sarcoma"):
            got = fetch_pages(
                client,
                {
                    "query.cond": term,
                    "filter.advanced": "AREA[StudyType]INTERVENTIONAL "
                    "AND AREA[InterventionType]DRUG",
                },
                cap=args.control_cap // 4,
                label=f"control:{term}",
            )
            for s in got:
                row = flatten(s)
                nct = row["nct_id"]
                if not nct or nct in adc or nct in controls:
                    continue
                if registry.find_agents(*row["interventions"], row["title"]):
                    continue  # an ADC trial the INN sweep missed; never a control
                if not row["eligibility"]:
                    continue
                controls[nct] = row
        print(f"\nControls: {len(controls):,}")
        if len(controls) < 500:
            raise SystemExit(f"control cohort too small ({len(controls)}); check the query")

    (args.out / "adc_trials.json").write_text(
        json.dumps(list(adc.values()), ensure_ascii=False), encoding="utf-8"
    )
    (args.out / "control_trials.json").write_text(
        json.dumps(list(controls.values()), ensure_ascii=False), encoding="utf-8"
    )
    manifest = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api": API,
        "fields": FIELDS,
        "n_adc": len(adc),
        "n_control": len(controls),
        "n_adc_with_eligibility": sum(1 for r in adc.values() if r["eligibility"]),
    }
    (args.out / "_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\n-> {args.out}  {json.dumps(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
