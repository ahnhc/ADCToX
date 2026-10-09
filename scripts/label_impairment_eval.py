"""Score the model's organ ranking against FDA label impairment guidance.

The plan calls this the one validation to build for the comorbidity layer, and the reason
is independence: a label's Use in Specific Populations section was written by a regulator
adjudicating a sponsor's data, it never saw this corpus, and it is not derived from trial
exclusion criteria -- so it does not share the circularity that makes exclusion recovery a
weak test of a hand-assigned mapping.

What the labels say is graded rather than boilerplate, which is what makes it scoreable.
ADCETRIS says to avoid severe renal impairment and moderate-to-severe hepatic impairment;
ENHERTU says no adjustment is needed for mild or moderate renal impairment; TRODELVY says
the dosage has not been established. Four levels, ordered by how much the regulator
restricts use.

Two things this test is not. It is 15 agents by 2 organs, so about 30 ordinal cells -- the
plan says so, and a result from 30 cells is a case series with a statistic attached rather
than a validation study. And the ordering of `not_established` is an assumption: it sits
above `avoid` here because a sponsor with no data in an organ is the most restrictive
position a label can take, but it is an absence of evidence rather than a finding, so the
analysis is repeated with it dropped.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

from adctox.provenance import stamp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Ordered by how much the label restricts use. `not_established` is placed above `avoid`
# because it is the most restrictive thing a label can say, and the analysis is also run
# without it -- see the module note.
LEVELS = {"no_adjustment": 0, "monitor": 1, "avoid": 2, "not_established": 3}

# Subsection headers inside Use in Specific Populations, e.g. "8.6 Renal Impairment".
# The text is whitespace-normalised before this runs, so splitting on the numbered header
# is the only reliable boundary.
#
# The first version used a lookahead on "\n" to end each section -- after the newlines had
# already been collapsed, so the lookahead could never fire and nine of fourteen renal
# sections came back as absent. The plan had measured renal text present in 13 of 14
# labels, which is what made the gap visible; without that figure a parser dropping twelve
# of twenty-eight cells would have looked like a thin corpus.
SUBSECTION = re.compile(r"(?:(?<=\s)|^)(\d{1,2}\.\d{1,2})\s+(?=[A-Z])")
ORGAN_HEADER = {
    "hepatic": re.compile(r"^hepatic\s+impairment", re.I),
    "renal": re.compile(r"^renal\s+impairment", re.I),
}

# Matched in this order; the first hit wins, because a section saying "avoid in severe"
# and "no adjustment in mild" is restricting use and the restriction is the claim.
GUIDANCE = (
    ("not_established", re.compile(
        r"(?:has\s+not\s+been\s+(?:established|studied|conducted)|"
        r"not\s+recommended\s+in|"
        r"no\s+dedicated\s+\w+\s+impairment\s+(?:trial|study)|"
        r"no\s+(?:data|information)\s+(?:are\s+|is\s+)?available)", re.I)),
    ("avoid", re.compile(r"\bavoid\b|\bcontraindicated\b|\bdo\s+not\s+(?:use|administer)",
                         re.I)),
    ("monitor", re.compile(
        r"monitor|reduce\s+the\s+dos|dosage\s+reduction\s+is\s+required|"
        r"dose\s+reduction", re.I)),
    ("no_adjustment", re.compile(
        r"no\s+(?:dose|dosage)\s+adjustment(?:\s+of\s+\S+)?\s+is\s+"
        r"(?:required|recommended|necessary)|"
        r"no\s+(?:dose|dosage)\s+adjustment\s+(?:is\s+)?(?:required|recommended)", re.I)),
)

# What the impairment section is actually *about*. This is the measurement that decides
# whether the ordinal test above is well posed, and it decided against it: of 19 impairment
# sections, 52.6% talk about pharmacokinetics -- exposure, clearance, AUC, unconjugated
# payload -- 26.3% about systemic adverse reactions and only 10.5% about an organ-specific
# event. ADCETRIS says "MMAE exposure and adverse reactions are increased"; inotuzumab
# ozogamicin says "based on a population pharmacokinetic analysis, the clearance ...".
#
# So a label's impairment guidance is a clearance argument, and the model predicts
# organ-specific event rates. The two are different quantities and a null correlation is
# the correct answer rather than a failure. Measured rather than asserted, because the plan
# designated this as the single validation to build.
PK_LANGUAGE = re.compile(
    r"exposure|clearance|pharmacokinetic|\bAUC\b|concentration|unconjugated"
    r"|free\s+(?:MMAE|MMAF|drug|payload)", re.I)
ORGAN_EVENT_LANGUAGE = re.compile(
    r"hepatotox|nephrotox|liver\s+(?:injury|enzyme|failure)|transaminase"
    r"|bilirubin\s+(?:increase|elevat)|renal\s+(?:failure|injury)|kidney\s+injury", re.I)
SYSTEMIC_LANGUAGE = re.compile(
    r"adverse\s+reactions?\s+(?:are\s+|were\s+)?(?:increased|greater|higher)"
    r"|grade\s*[\u22653]|deaths?", re.I)

# Cross-organ statements: a comorbidity in one organ raising the risk in another. The plan
# names these as the only test that separates the coupling term from plain tissue overlap,
# and as a case series of six to ten sentences rather than a statistic.
CROSS_ORGAN = re.compile(
    r"[^.]{0,200}?\b(?:higher|greater|increased)\s+(?:incidence|frequency|rate|exposure)"
    r"[^.]{0,200}?\b(?:hepatic|renal)\s+impairment[^.]{0,120}\.",
    re.I,
)


def section_text(label: dict, organ: str) -> str | None:
    """The organ's own subsection of Use in Specific Populations.

    Split on the numbered subsection headers and keep the block whose first words name the
    organ. Falling back to a window around the phrase would pull in the neighbouring
    organ's guidance, which is the one error that would silently swap two cells.
    """
    raw = label.get("use_in_specific_populations")
    if not raw:
        return None
    text = re.sub(r"\s+", " ", " ".join(raw) if isinstance(raw, list) else str(raw))
    parts = SUBSECTION.split(text)
    # `split` with one group yields [pre, num, body, num, body, ...].
    blocks = [parts[i + 1] for i in range(1, len(parts) - 1, 2)]
    for block in blocks:
        if ORGAN_HEADER[organ].match(block.strip()):
            return block.strip()
    # Some labels carry the heading without a number. Take the phrase to the next heading.
    m = re.search(
        rf"{organ}\s+impairment\b(.{{0,1500}}?)"
        rf"(?=(?:hepatic|renal|pediatric|geriatric|lactation|pregnan)\s|$)",
        text, re.I)
    return m.group(1).strip() if m else None


def grade(text: str | None) -> tuple[str | None, str]:
    if not text:
        return None, ""
    for name, pat in GUIDANCE:
        m = pat.search(text)
        if m:
            start = max(0, m.start() - 60)
            return name, text[start:m.end() + 90].strip()
    return None, text[:120]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=pathlib.Path, required=True)
    ap.add_argument("--posterior", type=pathlib.Path,
                    default=ROOT / "artifacts" / "posterior_other.npz")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "label_impairment_eval.json")
    args = ap.parse_args()

    import yaml

    from adctox.model.predict import Posterior, predict_draws

    post = Posterior.load(args.posterior)
    registry = yaml.safe_load(
        (ROOT / "conf" / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]

    cells: list[dict] = []
    cross: list[dict] = []
    missing: list[dict] = []
    for path in sorted(args.labels.glob("*.json")):
        agent = path.stem
        if agent == "_manifest" or agent not in registry:
            continue
        spec = registry[agent]
        label = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(label, dict) and "results" in label:
            label = label["results"][0]

        # The model's predicted rate for this agent's own chemistry, per organ.
        #
        # `include_agent_variation=False` on purpose. That term is a draw from the fitted
        # agent-level residual and belongs in a prediction for a *new* molecule; here the
        # molecule is the one whose label is being read, so adding a random agent
        # deviation would be predicting a different drug of the same chemistry.
        draws = predict_draws(
            post,
            mechanisms=[spec["mechanism"]],
            families=[spec["payload_family"]],
            dars=np.array(
                [float(spec["dar"]) if spec.get("dar") else post.dar_mean]
            ),
            cleavables=np.array([float(bool(spec["linker_cleavable"]))]),
            include_agent_variation=False,
        )
        rates = {a: float(draws[:, 0, i].mean()) for i, a in enumerate(post.axes)}

        for organ in ("hepatic", "renal"):
            text = section_text(label, organ)
            level, evidence = grade(text)
            if level is None:
                missing.append({"agent": agent, "organ": organ,
                                "reason": "no gradable guidance found",
                                "section_present": text is not None})
                continue
            cells.append({
                "agent": agent, "organ": organ, "level": level,
                "level_rank": LEVELS[level],
                "model_rate": round(rates.get(organ, float("nan")), 4),
                "evidence": evidence[:220],
                # What this section argues from, which is what decides whether the cell
                # is comparable to an organ-specific event rate at all.
                "mentions_pharmacokinetics": bool(PK_LANGUAGE.search(text)),
                "mentions_organ_event": bool(ORGAN_EVENT_LANGUAGE.search(text)),
                "mentions_systemic_reactions": bool(SYSTEMIC_LANGUAGE.search(text)),
            })

        blob = re.sub(
            r"\s+", " ",
            " ".join(label.get("use_in_specific_populations") or [])
            + " " + " ".join(label.get("warnings_and_cautions") or []),
        )
        for m in CROSS_ORGAN.finditer(blob):
            cross.append({"agent": agent, "sentence": m.group(0).strip()[:300]})

    print(f"라벨 {len(set(c['agent'] for c in cells))}종에서 순서형 셀 {len(cells)}개 "
          f"(미추출 {len(missing)})")
    by_level: dict[str, int] = {}
    for c in cells:
        by_level[c["level"]] = by_level.get(c["level"], 0) + 1
    print("  수준 분포:", by_level)

    n_pk = sum(1 for c in cells if c["mentions_pharmacokinetics"])
    n_organ = sum(1 for c in cells if c["mentions_organ_event"])
    n_sys = sum(1 for c in cells if c["mentions_systemic_reactions"])
    print(f"\n장애 섹션이 무엇을 논하는가 ({len(cells)}개 셀)")
    print(f"  약동학 (노출/청소율)      {n_pk:3d}  "
          f"{100.0 * n_pk / max(1, len(cells)):5.1f}%")
    print(f"  장기 특이 사건            {n_organ:3d}  "
          f"{100.0 * n_organ / max(1, len(cells)):5.1f}%")
    print(f"  전신 이상반응             {n_sys:3d}  "
          f"{100.0 * n_sys / max(1, len(cells)):5.1f}%")
    print("  → 라벨의 장애 항목은 청소율 논증이고 모델은 장기별 사건률을 예측합니다.")
    print("     서로 다른 양이므로 아래 상관의 귀무는 모델의 실패가 아닙니다.")

    out: dict = {
        "provenance": stamp({"posterior": args.posterior}),
        "what_the_sections_argue_from": {
            "n_cells": len(cells),
            "mentions_pharmacokinetics": n_pk,
            "mentions_organ_event": n_organ,
            "mentions_systemic_reactions": n_sys,
            "pharmacokinetic_share": n_pk / len(cells) if cells else None,
            "organ_event_share": n_organ / len(cells) if cells else None,
            "note": (
                "A label's impairment guidance argues from clearance and exposure; the "
                "model predicts organ-specific event rates. The ordinal correlation below "
                "compares two different quantities, which is why its null is the correct "
                "answer and not a failed validation."
            ),
        },
        "levels": LEVELS,
        "n_cells": len(cells),
        "cells": cells,
        "missing": missing,
        "cross_organ_sentences": cross,
    }

    for tag, subset in (
        ("all_levels", cells),
        ("without_not_established",
         [c for c in cells if c["level"] != "not_established"]),
    ):
        ranks = [c["level_rank"] for c in subset]
        rates = [c["model_rate"] for c in subset]
        ok = [i for i, r in enumerate(rates) if r == r]
        if len(set(ranks)) < 2 or len(ok) < 6:
            print(f"\n{tag}: 셀 {len(subset)}개로는 상관을 계산하지 않습니다")
            out[tag] = {"n": len(subset), "spearman": None}
            continue
        rho = stats.spearmanr([ranks[i] for i in ok], [rates[i] for i in ok])
        print(f"\n{tag}: 셀 {len(ok)}개  Spearman rho {rho.statistic:+.3f}  "
              f"p {rho.pvalue:.4f}")
        out[tag] = {
            "n": len(ok), "spearman": float(rho.statistic),
            "p": float(rho.pvalue),
            "n_distinct_levels": len(set(ranks)),
        }

    print("\n셀 (라벨 수준 → 모델 예측률)")
    for c in sorted(cells, key=lambda c: (c["organ"], c["level_rank"])):
        print(f"  {c['agent']:26s} {c['organ']:8s} {c['level']:16s} "
              f"{c['model_rate']:.4f}")

    print(f"\n교차장기 문장 {len(cross)}건")
    for x in cross[:8]:
        print(f"  {x['agent']:26s} {x['sentence'][:150]}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
