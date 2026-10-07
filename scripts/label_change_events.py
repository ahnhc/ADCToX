#!/usr/bin/env python
"""Enumerate dated organ-warning additions across every ADC label version."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.provenance import write_json  # noqa: E402

from adctox.validation.label_change import diff_versions, parse_version  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((args.raw / "_manifest.json").read_text(encoding="utf-8"))
    all_events = []
    unmapped_total: Counter[str] = Counter()
    parsed_counts = {}

    for agent, spec in manifest["agents"].items():
        adir = args.raw / agent
        if not adir.exists():
            continue
        dates = {v["version"]: v.get("date") for v in spec.get("versions", [])}
        versions = []
        for path in sorted(adir.glob("v*.html"), key=lambda p: int(p.stem[1:])):
            num = int(path.stem[1:])
            try:
                versions.append(parse_version(path, agent, num, dates.get(num)))
            except Exception as exc:  # a malformed page must not take the run down
                print(f"  ! {agent} v{num}: {exc}", file=sys.stderr)
        if not versions:
            continue
        parsed_counts[agent] = len(versions)
        for v in versions:
            unmapped_total.update(v.unmapped)
        events = diff_versions(versions)
        all_events.extend(events)
        first = min(versions, key=lambda v: v.version)
        print(
            f"  {agent:26s} {len(versions):3d} versions  "
            f"first axes at v{first.version}: {','.join(sorted(first.axes))}"
        )

    added = [e for e in all_events if e.kind == "axis_added"]
    escalated = [e for e in all_events if e.kind == "escalated_to_boxed"]

    print(f"\n{'=' * 78}\nOrgan axes ADDED after the first available label version\n{'=' * 78}")
    print(f"  {'agent':26s} {'date':12s} {'axis':20s} heading")
    for e in sorted(added, key=lambda e: (e.date or "", e.agent)):
        mark = " *" if e.needs_adjudication else ""
        print(f"  {e.agent:26s} {str(e.date):12s} {e.axis:20s} {e.heading[:38]}{mark}")
    print(f"\n  {len(added)} additions, {sum(e.needs_adjudication for e in added)} "
          f"marked * for hand adjudication (the previous version had an unrecognized "
          f"heading, so a rename cannot be ruled out from the diff alone)")

    print(f"\nSeverity escalations into the boxed warning ({len(escalated)})")
    for e in sorted(escalated, key=lambda e: (e.date or "", e.agent)):
        print(f"  {e.agent:26s} {str(e.date):12s} {e.axis:20s} {e.heading[:52]}")

    per_agent = Counter(e.agent for e in added)
    print(f"\nAdditions per agent -- concentration matters for the power calculation")
    for agent, n in per_agent.most_common():
        print(f"  {n:2d}  {agent}")
    if per_agent:
        top, top_n = per_agent.most_common(1)[0]
        print(f"\n  {top_n} of {len(added)} additions come from {top} alone. Effective "
              f"independent drugs is {len(per_agent)}, not the event count, and any test "
              f"must report a leave-{top.split('_')[0]}-out sensitivity.")

    if unmapped_total:
        print(f"\nUnmapped section-5 headings ({len(unmapped_total)} distinct) -- these are "
              f"reported rather than dropped, since a missed mapping would hide an event")
        for heading, n in unmapped_total.most_common(12):
            print(f"  {n:3d}  {heading[:66]}")

    out = {
        "n_agents": len(parsed_counts),
        "versions_parsed": parsed_counts,
        "axis_additions": [vars(e) for e in added],
        "boxed_escalations": [vars(e) for e in escalated],
        "additions_per_agent": dict(per_agent),
        "unmapped_headings": dict(unmapped_total),
    }
    path = args.out / "label_change_events.json"
    write_json(path, out, {"raw": args.raw})
    print(f"\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
