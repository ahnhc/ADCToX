"""Measure whether the literature path can actually add agents to the corpus.

This is the feasibility gate for the whole extraction effort, run before the extractor is
wired to the model rather than after. The obvious thing to measure is the per-table yield,
and the project plan did: 2.1% of AE tables image-only, 86.8% of cells reproducing their
printed percentage. Both are re-measured here on this corpus instead of being quoted.

But the per-table rate is not the decision-relevant number, and assuming it was would have
been a mistake. Measured on the first eight articles fetched: Haematologica deposits
*every* table as a `.jpg`, including the LOTIS-2 treatment-emergent adverse event table.
A 2% global average hides that, because the loss is concentrated in journals rather than
spread across them -- and ADCs are disproportionately haematological, so the journals most
likely to be image-only are the ones carrying the agents the corpus is shortest on.

The number that decides the question is therefore **per agent**: does this agent have at
least one machine-readable adverse-event table with counts and a denominator, from any
journal? Redundancy rescues agents that any single journal would lose -- the same LOTIS-2
safety table also appears in a Blood Advances report. An agent is added to the corpus or it
is not; it does not matter which of its papers supplied the table.

So the headline here is a count of recoverable agents, and the per-journal and per-cell
rates are reported underneath as diagnostics for why specific agents fail.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from adctox.extract.denominator import fill as fill_denominators  # noqa: E402
from adctox.extract.jats_tables import ARITHMETIC_TOLERANCE_PP  # noqa: E402
from adctox.extract.jats_tables import parse_article  # noqa: E402
from adctox.provenance import stamp  # noqa: E402

# A table is only useful to a hierarchical binomial if it yields a numerator and a
# denominator. A table of bare percentages gives a rate with no weight, which the model
# cannot distinguish from a rate measured on three patients.
MIN_USABLE_CELLS = 3


def _listing_digest(d: pathlib.Path) -> pathlib.Path:
    """`stamp` hashes files and the input here is a directory, so hash the file list."""
    lines = [f"{p.name}\t{p.stat().st_size}" for p in sorted(d.glob("*.xml"))]
    out = d.parent / "_xml_listing.tsv"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:5.1f}%" if d else "    --"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=pathlib.Path, required=True,
                    help="the fetch output directory, holding xml/ and _manifest.json")
    ap.add_argument("--out", type=pathlib.Path, default=None)
    args = ap.parse_args()

    xml_dir = args.raw_dir / "xml"
    manifest = json.loads((args.raw_dir / "_manifest.json").read_text(encoding="utf-8"))
    records: dict[str, dict] = manifest["records"]

    paths = sorted(xml_dir.glob("*.xml"))
    if not paths:
        print(f"no xml under {xml_dir}", file=sys.stderr)
        return 1

    per_journal: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    per_agent: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    # Why each agent failed, when it did -- the diagnostic that says whether a second
    # fetch would help or whether the agent is simply not recoverable this way.
    agent_journals: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    totals = collections.Counter()
    cells_ok = cells_checked = 0
    deltas: list[float] = []
    failures: list[dict] = []

    for p in paths:
        pmcid = p.stem.removeprefix("PMC")
        agent = records.get(pmcid, {}).get("agent_hint", "(unattributed)")
        try:
            meta, tables = parse_article(p)
        except Exception as exc:  # a malformed deposit is a measurement, not a crash
            totals["unparseable_article"] += 1
            failures.append({"path": p.name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        journal = meta["journal"] or "(no journal-title)"
        totals["articles"] += 1
        per_journal[journal]["articles"] += 1
        per_agent[agent]["articles"] += 1
        for t in tables:
            totals["tables"] += 1
            per_journal[journal]["tables"] += 1
            if not t.looks_like_ae_table:
                continue
            for bucket in (totals, per_journal[journal], per_agent[agent]):
                bucket["ae_tables"] += 1
            agent_journals[agent][journal] += 1
            if t.is_image_only:
                for bucket in (totals, per_journal[journal], per_agent[agent]):
                    bucket["ae_image_only"] += 1
                continue
            if not t.cells:
                totals["ae_no_cells"] += 1
                per_agent[agent]["ae_no_cells"] += 1
                continue
            # The same denominator recovery the extractor uses, so this gate measures the
            # pipeline rather than a weaker version of it. 44% of count-carrying AE tables
            # state no denominator in the header; see extract/denominator.py.
            recovered = fill_denominators(t, tables)
            if recovered:
                totals["denominator_recovered_tables"] += 1
                totals["denominator_recovered_columns"] += len(recovered)
            denom_of = dict(t.column_denominators)
            denom_of.update({col: got.value for col, got in recovered.items()})
            if not any(c.n is not None or c.pct is not None for c in t.cells):
                # No parseable rate cell at all. The two causes need different work, so
                # they are counted apart: a caption disclaiming rates means the AE detector
                # over-fired and nothing is lost, while the rest is a table the parser
                # cannot read or one that holds no rates to read. Measured decomposition of
                # 131 such tables: 29% disclaim, 62% have no recoverable numeric format,
                # and 9% declare their percentages in the header -- of which only 2 also
                # state a denominator, both in one review, so that format is not worth
                # parsing.
                totals["ae_no_rate_cells"] += 1
                totals[
                    "ae_caption_disclaims_rates" if t.caption_disclaims_rates
                    else "ae_no_parseable_rate_format"
                ] += 1
                continue
            usable = [
                c for c in t.cells if c.n is not None and denom_of.get(c.col)
            ]
            if len(usable) >= MIN_USABLE_CELLS:
                totals["ae_usable"] += 1
                per_agent[agent]["ae_usable"] += 1
                per_journal[journal]["ae_usable"] += 1
                totals["usable_cells"] += len(usable)
                per_agent[agent]["usable_cells"] += len(usable)
            elif any(c.n is not None for c in t.cells):
                totals["ae_counts_no_denominator"] += 1
                per_agent[agent]["ae_counts_no_denominator"] += 1
            else:
                totals["ae_pct_only"] += 1
                per_agent[agent]["ae_pct_only"] += 1
            # Re-check against the recovered denominators, not only the stated ones:
            # `t.checkable` was computed before recovery ran, so using it would measure
            # the gate on a strict subset and understate the corpus.
            for c in t.cells:
                d = denom_of.get(c.col)
                if c.n is None or c.pct is None or not d:
                    continue
                cells_checked += 1
                delta = abs(100.0 * c.n / d - c.pct)
                cells_ok += delta <= ARITHMETIC_TOLERANCE_PP
                deltas.append(delta)

    # ---- headline: agents recovered -------------------------------------------------
    agents_sought = sorted({r["agent_hint"] for r in records.values()})
    recovered = [a for a in agents_sought if per_agent[a]["ae_usable"] > 0]
    image_only_loss = [
        a for a in agents_sought
        if per_agent[a]["ae_usable"] == 0 and per_agent[a]["ae_image_only"] > 0
    ]
    no_ae_table = [
        a for a in agents_sought
        if per_agent[a]["ae_usable"] == 0 and per_agent[a]["ae_tables"] == 0
    ]

    print(f"약물 {len(agents_sought)}종 검색, 논문 {totals['articles']}편 파싱, "
          f"표 {totals['tables']}개, AE 표 {totals['ae_tables']}개")
    # A silent parse failure is the worst possible outcome for a feasibility gate: it
    # reports a low yield and attributes it to the corpus. This counter was incremented
    # and never printed, and 211 articles failed behind it on a NameError while the script
    # cheerfully reported "0 tables".
    if totals["unparseable_article"]:
        print(f"  !! 파싱 실패 논문 {totals['unparseable_article']}편 "
              f"— 아래 수율은 그만큼 과소평가입니다")
        for f in failures[:5]:
            print(f"     {f['path']}: {f['error'][:90]}")
    print()
    print(f"★ 기계판독 가능한 AE 표를 1개 이상 가진 약물: "
          f"{len(recovered)}/{len(agents_sought)} "
          f"({_pct(len(recovered), len(agents_sought)).strip()})")
    print(f"  이미지 전용 때문에 0인 약물   {len(image_only_loss):3d}  "
          f"{', '.join(image_only_loss[:6]) or '-'}")
    print(f"  AE 표 자체가 없는 약물        {len(no_ae_table):3d}  "
          f"{', '.join(no_ae_table[:6]) or '-'}")
    print()
    print(f"  {'agent':30s} {'논문':>4s} {'AE표':>5s} {'IMG':>4s} "
          f"{'사용가능':>7s} {'셀':>6s}")
    for a in agents_sought:
        c = per_agent[a]
        mark = " " if c["ae_usable"] else "✗"
        print(f"{mark} {a:30s} {c['articles']:4d} {c['ae_tables']:5d} "
              f"{c['ae_image_only']:4d} {c['ae_usable']:7d} {c['usable_cells']:6d}")

    # ---- diagnostics ----------------------------------------------------------------
    ae = totals["ae_tables"]
    print()
    print("AE 표의 운명")
    for key, label in [
        ("ae_image_only", "이미지 전용 (버림)"),
        ("ae_no_cells", "빈 격자"),
        ("ae_usable", f"분자+분모 {MIN_USABLE_CELLS}셀 이상 (사용)"),
        ("ae_counts_no_denominator", "분자만, 분모 미기재"),
        ("ae_pct_only", "퍼센트만 (분자 없음)"),
        ("ae_no_rate_cells", "비율 셀 없음"),
        ("ae_caption_disclaims_rates", "  캡션이 비율표가 아니라고 함 (탐지기 위양성)"),
        ("ae_no_parseable_rate_format", "  파싱 가능한 비율 포맷 없음"),
    ]:
        print(f"  {label:34s} {totals[key]:5d}  {_pct(totals[key], ae)}")

    print()
    print(f"산술 게이트: {cells_ok}/{cells_checked} 셀 통과 "
          f"({_pct(cells_ok, cells_checked).strip()})   [계획서 실측 86.8%]")
    if deltas:
        deltas.sort()
        print(f"  |100·n/N − pct| 중앙값 {deltas[len(deltas) // 2]:.3f}pp, "
              f"90분위 {deltas[int(0.9 * len(deltas))]:.3f}pp")

    print()
    print("저널별 이미지 전용 비율 (AE 표 2개 이상)")
    rows = sorted(
        ((j, c["ae_tables"], c["ae_image_only"]) for j, c in per_journal.items()
         if c["ae_tables"] >= 2),
        key=lambda r: (-(r[2] / r[1]), -r[1]),
    )
    shown = 0
    print(f"  {'journal':46s} {'AE표':>5s} {'IMG':>5s} {'비율':>7s}")
    for j, n_ae, n_img in rows:
        if n_img == 0:
            continue
        print(f"  {j[:46]:46s} {n_ae:5d} {n_img:5d} {_pct(n_img, n_ae):>7s}")
        shown += 1
    print(f"  (이미지 전용 0인 저널 {len(rows) - shown}/{len(rows)}개 생략)")

    out = {
        "provenance": stamp({"xml_listing": _listing_digest(xml_dir)}),
        "agents": {
            "sought": agents_sought,
            "recovered": recovered,
            "lost_to_image_only": image_only_loss,
            "no_ae_table_found": no_ae_table,
            "per_agent": {a: dict(per_agent[a]) for a in agents_sought},
            "journals_per_agent": {
                a: dict(agent_journals[a]) for a in agents_sought if agent_journals[a]
            },
        },
        "totals": dict(totals),
        "arithmetic": {
            "cells_checked": cells_checked,
            "cells_passed": cells_ok,
            "pass_rate": (cells_ok / cells_checked) if cells_checked else None,
            "plan_claimed_pass_rate": 0.868,
            "median_delta_pp": (deltas[len(deltas) // 2] if deltas else None),
        },
        "by_journal": {j: dict(c) for j, c in sorted(per_journal.items())},
        "unparseable": failures,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
