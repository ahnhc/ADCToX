"""Can the missing DAR values be recovered from the articles already harvested?

Twelve of the registry's 34 conventional conjugates have no stated drug-to-antibody ratio,
and that is what limits the comparator's reference set to 22 chemistries: an agent with no
DAR cannot be predicted from, and giving it the corpus mean would seat it at the centre of
every comparison on the strength of a missing value.

So the question is whether the 1,496 open-access articles already on disk state it. The
answer is measured here rather than assumed, and it is no: the search finds a candidate for
two of the twelve, one of those from a review rather than a primary report.

It also finds the trap that makes a naive version of this harmful. A population-PK paper
labels its conjugate species `DAR0` through `DAR8` -- one molecule of payload, two, and so
on -- and those tokens sit beside the agent's name in the same sentence. Read as the
conjugate's DAR they would assign tusamitamab ravtansine a value of 1 or of 8, both wrong,
and nothing downstream would flag it. The pattern therefore refuses a `DARn` token that
appears in a sentence naming a span of them.
"""

from __future__ import annotations

import argparse
import pathlib
import re

import yaml
from lxml import etree

from adctox.provenance import write_json

ROOT = pathlib.Path(__file__).resolve().parents[1]

# `DAR 4`, `DAR4`, `DAR of 4`, `drug-to-antibody ratio of 8`, `DAR ~4`, `DAR 3.5-4`.
DAR = re.compile(
    r"(?:drug[-\s]to[-\s]antibody\s+ratio|DAR)\s*(?:\(DAR\))?\s*"
    r"(?:of|was|is|=|:|~|approximately|about)?\s*"
    r"(\d(?:\.\d+)?)(?:\s*(?:[-–]|to)\s*(\d(?:\.\d+)?))?",
    re.I,
)
# A sentence that enumerates conjugate species -- "from DAR1 (i.e. ADC with one DM4
# molecule) to DAR8" -- describes a mixture, not the agent's nominal ratio, and those tokens
# sit beside the agent's name: read as the ratio they would give tusamitamab ravtansine a
# DAR of 1 or of 8. A separate pattern for the span was tried and dropped. Finding the
# sentence boundary with dots does not work on the one sentence it was written for, because
# "i.e." ends in a dot before a space exactly as a sentence does, and a check that silently
# fails to fire is worse than no check. The gloss below decides it instead, on the words
# that distinguish a species from a ratio.
SPECIES_GLOSS = re.compile(
    r"(?:species|molecule[s]?\s+(?:per|bound)|one\s+\w+\s+molecule|"
    r"\bbearing\b|\bper\s+antibody\b)", re.I
)
# The statement that answers the question. An ADC's DAR is a distribution, so the figure a
# registry wants is the mean of the administered solution, and papers say so in words.
AVERAGE = re.compile(r"\b(?:average|mean|nominal)\b", re.I)
# A bare `DAR4` with no verb is how reviews tabulate the nominal value, and also how PK
# papers name a species. Integer-valued and unqualified, it needs the other signals to tell
# which it is.
BARE = re.compile(r"^DAR\s*\d+$", re.I)
WINDOW = 160
# How far before a number the qualifier may sit. "with an average DAR of 3.8" is
# 25 characters; anything longer starts picking up the previous clause.
LOOKBACK = 30


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmc", type=pathlib.Path,
                    default=pathlib.Path("/data/hyeongchanahn/adctox/raw/pmc"))
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "dar_gap.json")
    args = ap.parse_args()

    reg = yaml.safe_load(
        (ROOT / "conf" / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]
    missing = {
        k: s for k, s in reg.items()
        if s.get("conventional_adc") and s.get("dar") is None
    }
    names = {
        k: [s["inn"].lower()] + [a.lower() for a in (s.get("aliases") or [])]
        for k, s in missing.items()
    }

    files = sorted(args.pmc.rglob("*.xml"))
    mentioned: dict[str, set[str]] = {k: set() for k in missing}
    candidates: dict[str, list[dict]] = {k: [] for k in missing}

    for f in files:
        try:
            tree = etree.parse(str(f))
            text = etree.tostring(tree, method="text", encoding="unicode")
        except (etree.XMLSyntaxError, OSError):
            continue
        # The same guard the extraction pipeline uses for attribution, and for the same
        # reason. PMC12146481 is a preclinical paper about *mecbotamab* vedotin that
        # mentions enapotamab vedotin in its introduction, carrying "DAR4" beside the name.
        # A background sentence in another drug's paper is not that drug's primary report,
        # and the loose version of this test is what turned 13 attributable agents into 52.
        head = " ".join(
            (t or "")
            for t in (
                [tree.findtext(".//article-title")]
                + [etree.tostring(a, method="text", encoding="unicode")
                   for a in tree.findall(".//abstract")]
            )
        ).lower()
        low = text.lower()
        here = [k for k, forms in names.items() if any(n in low for n in forms)]
        if not here:
            continue
        for k in here:
            mentioned[k].add(f.stem)
        for m in DAR.finditer(text):
            ctx = re.sub(
                r"\s+", " ", text[max(0, m.start() - WINDOW):m.end() + 60]
            )
            frag = m.group(0).strip()
            # The qualifier has to sit immediately before the match, not anywhere in the
            # window. "The maximum average DAR reduces from 3.3 to 2.8 due to the
            # accumulation of DAR0 and DAR1" carries the word `average` thirty characters
            # ahead of two species labels, and a window-wide test read both of them as
            # average statements -- which is why this agent's three "average" matches
            # disagreed and the usable value came back empty.
            #
            # A bare `DARn` is never an average statement either: the nominal figure is
            # always written with a connector ("DAR of 3.8", "average DAR was 4").
            lookback = text[max(0, m.start() - LOOKBACK):m.start()]
            if AVERAGE.search(lookback) and not BARE.match(frag):
                reading = "average"
            elif BARE.match(frag) and SPECIES_GLOSS.search(ctx):
                reading = "species_label"
            else:
                reading = "unqualified"
            for k in here:
                if any(n in ctx.lower() for n in names[k]):
                    candidates[k].append({
                        "pmcid": f.stem, "match": frag,
                        "value": float(m.group(1)),
                        "reading": reading,
                        "primary": any(n in head for n in names[k]),
                        "context": ctx[:260],
                    })

    rows = []
    for k in sorted(missing):
        primary = [c for c in candidates[k] if c["primary"]]
        avg = [c for c in primary if c["reading"] == "average"]
        unq = [c for c in primary if c["reading"] == "unqualified"]
        usable = avg or unq
        values = sorted({c["value"] for c in usable})
        rows.append({
            "agent": k,
            "inn": missing[k]["inn"],
            "articles_mentioning": len(mentioned[k]),
            "dar_candidates": len(candidates[k]),
            "n_average_statements": len(avg),
            "n_in_a_paper_about_this_agent": len(primary),
            "n_species_labels": sum(
                1 for c in candidates[k] if c["reading"] == "species_label"
            ),
            # Only where the usable statements agree. Two different figures for one agent is
            # a question for a human, not a value to write into a registry.
            "usable_value": values[0] if len(values) == 1 else None,
            "values_seen": sorted({c["value"] for c in candidates[k]}),
            "evidence": usable[:3] or candidates[k][:3],
        })
    summary = {
        "articles_searched": len(files),
        "agents_without_a_dar": len(missing),
        "agents_with_a_candidate": sum(1 for r in rows if r["dar_candidates"]),
        "agents_with_one_usable_value": sum(
            1 for r in rows if r["usable_value"] is not None
        ),
        "agents_with_an_average_statement": sum(
            1 for r in rows if r["n_average_statements"]
        ),
        "agents_never_mentioned": sum(
            1 for r in rows if r["articles_mentioning"] == 0
        ),
        "species_label_matches_rejected": sum(
            1 for v in candidates.values()
            for c in v if c["reading"] == "species_label"
        ),
    }

    print(f"  {'agent':30s} {'arts':>5s} {'cand':>5s} {'own':>4s} {'avg':>4s} "
          f"{'spec':>5s} {'usable':>7s}  values seen")
    for r in rows:
        print(f"  {r['agent']:30s} {r['articles_mentioning']:5d} "
              f"{r['dar_candidates']:5d} {r['n_in_a_paper_about_this_agent']:4d} "
              f"{r['n_average_statements']:4d} "
              f"{r['n_species_labels']:5d} {str(r['usable_value']):>7s}  "
              f"{r['values_seen']}")
    print()
    for k, v in summary.items():
        print(f"  {k:34s} {v}")

    write_json(args.out, {"summary": summary, "agents": rows})
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
