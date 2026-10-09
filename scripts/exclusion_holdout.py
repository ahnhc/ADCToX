"""Test the comorbidity organ mapping against trial exclusion criteria, non-circularly.

The plan's strongest claim about the comorbidity layer is this one. A hand-assigned
condition-to-organ mapping cannot be validated against exclusion criteria, because it was
written by reading them; the only non-circular holdout left is about 28 cells of FDA label
impairment text. A MONDO `is_a` closure never saw the text, so recovering exclusion
criteria from it is legitimate -- over 3,762 trials rather than 28 cells.

**The circularity does not disappear by itself, and most of it is on the other side.** The
organ-concern rules were also written by reading exclusion criteria, and several of them
*are* condition names: the hepatic rules contain `cirrhosis`, the neurologic rules contain
`peripheral neuropath`, the gastrointestinal rules contain `inflammatory bowel|crohn`, the
infectious rules contain `hepatitis [bc]` and `hiv`. For those conditions, "this trial
mentions the condition" and "this trial flags the organ" are the same regular expression,
and the test would measure nothing at all.

So for each condition, the patterns its own name matches are removed before its trials are
flagged. What remains for cirrhosis on the hepatic axis is bilirubin, AST/ALT, Child-Pugh
and "hepatic impairment" -- and whether a trial that excludes cirrhosis also sets a
bilirubin threshold is a real question with a real answer.

The hand map is scored alongside, and it is expected to score *higher* precisely because it
is circular. That contrast is the measurement, not a defeat.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adctox.extract.organ_concern import OrganConcernExtractor  # noqa: E402
from adctox.provenance import stamp  # noqa: E402
from audit_mondo_ids import parse_synonyms  # noqa: E402
from derive_organ_axes import parse_obo  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "comorbidity_registry.csv"
DERIVED = ROOT / "artifacts" / "mondo_organ_axes.json"

# A condition needs this many mentioning trials before its enrichment means anything.
MIN_TRIALS = 20
# A matcher hitting more than this share of the corpus is matching something generic
# rather than the condition. Six conditions tripped it: they are pinned to the MONDO root
# as a deliberate "no disease term applies", and the root's own synonyms -- "disease",
# "disorder" and their variants -- were being fed into the matcher, which then matched 60%
# of all trials. Their enrichments were identical to three decimals, which is what gave it
# away.
MAX_CORPUS_SHARE = 0.25
# The ontology root. Conditions pinned to it have no MONDO name worth matching and derive
# no organ, so they cannot contribute a positive cell -- including them only adds
# 6 x 11 = 66 negative cells of noise to the AUROC.
ROOT_TERM = "MONDO:0000001"


def condition_matcher(label: str, mondo_name: str | None,
                      synonyms: set[str]) -> re.Pattern[str] | None:
    """A regex matching this condition by name in eligibility prose.

    Built from the registry label, the MONDO term name and MONDO's EXACT synonyms, with
    qualifiers stripped -- a protocol writes "cirrhosis", not "Cirrhosis (Child-Pugh B/C)".
    Short or generic forms are dropped: a 4-character synonym matches half the corpus.
    """
    forms = {label.lower()}
    if mondo_name:
        forms.add(mondo_name.lower())
    forms |= {s.lower() for s in synonyms}
    cleaned: set[str] = set()
    for f in forms:
        f = re.sub(
            r"\b(chronic|severe|active|prior|history of|controlled|reduced|stage\s*\S+)\b",
            " ", f)
        f = re.sub(r"[^a-z0-9 ]+", " ", f).strip()
        f = re.sub(r"\s+", " ", f)
        if len(f) >= 6 and f not in {"disease", "disorder", "syndrome"}:
            cleaned.add(f)
    if not cleaned:
        return None
    alts = "|".join(re.escape(f) for f in sorted(cleaned, key=len, reverse=True))
    return re.compile(rf"(?<![a-z]){alts}(?![a-z])", re.I)


def _auroc(scores: list[float], labels: list[int]) -> float | None:
    """Rank AUROC with ties at 0.5, which matters here because many enrichments tie."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum(
        1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg
    )
    return wins / (len(pos) * len(neg))


def permutation_p(
    pairs: list[dict], metric: str, key: str, n_perm: int = 2000, seed: int = 20261009
) -> dict:
    """AUROC's null distribution, shuffling axis assignments *within* each condition.

    The 11 cells of one condition are not independent -- their shares sum to one -- so an
    AUROC standard error computed over 293 cells would treat 27 conditions as 293. The
    permutation keeps each condition's number of assigned axes fixed and reassigns which
    axes they are, which is the exact null "this mapping knows nothing about organs" while
    preserving everything else about the corpus.
    """
    import random

    rng = random.Random(seed)
    rows = [p for p in pairs if p[metric] is not None]
    by_cond: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_cond[r["condition"]].append(r)

    scores = [r[metric] for r in rows]
    observed = _auroc(scores, [int(r[key]) for r in rows])
    if observed is None:
        return {"auroc": None, "p": None, "n_permutations": 0}

    ge = 0
    null: list[float] = []
    for _ in range(n_perm):
        labels: list[int] = []
        shuffled: dict[str, set[int]] = {}
        for cid, group in by_cond.items():
            k = sum(1 for r in group if r[key])
            picks = set(rng.sample(range(len(group)), k)) if k else set()
            shuffled[cid] = picks
        seen: dict[str, int] = collections.defaultdict(int)
        for r in rows:
            i = seen[r["condition"]]
            seen[r["condition"]] += 1
            labels.append(1 if i in shuffled[r["condition"]] else 0)
        a = _auroc(scores, labels)
        if a is not None:
            null.append(a)
            ge += a >= observed
    return {
        "auroc": observed,
        "p": (ge + 1) / (len(null) + 1) if null else None,
        "n_permutations": len(null),
        "null_mean": (sum(null) / len(null)) if null else None,
        "null_p95": (sorted(null)[int(0.95 * len(null))] if null else None),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--obo", type=pathlib.Path, required=True)
    ap.add_argument("--eligibility", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "exclusion_holdout.json")
    args = ap.parse_args()

    names, _ = parse_obo(args.obo)
    synonyms = parse_synonyms(args.obo)
    extractor = OrganConcernExtractor()
    axes = list(extractor.organs)
    derived = json.loads(DERIVED.read_text(encoding="utf-8"))["derived"]
    rows = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))

    trials: list[dict] = []
    for fname in ("adc_trials.json", "control_trials.json"):
        path = args.eligibility / fname
        if path.exists():
            for t in json.loads(path.read_text(encoding="utf-8")):
                if t.get("eligibility"):
                    trials.append(t)
    print(f"자격 텍스트가 있는 시험 {len(trials)}건")

    # Per-trial: which patterns fired, by organ. Computed once; the per-condition pass
    # then subtracts that condition's own patterns rather than re-running the regexes.
    fired: list[dict[str, set[str]]] = []
    texts: list[str] = []
    for t in trials:
        text = t["eligibility"]
        texts.append(text)
        hit = extractor.extract(text)
        fired.append({organ: set(e["patterns"]) for organ, e in hit.items()})

    base = {
        axis: sum(1 for f in fired if axis in f) / len(fired) for axis in axes
    }

    # A trial's *share* of concern on each axis, which is what removes the confound that
    # dominates the raw rate. Any trial detailed enough to name a comorbidity is detailed
    # enough to set thresholds on several organs, so conditions mentioned in long protocols
    # come out enriched on every axis at once -- which is why `ocular` was the top-enriched
    # axis for both cirrhosis and chronic kidney disease. Shares sum to one within a trial,
    # so protocol length cancels. Same confound as the reporting-channel artifact the plan
    # names for FAERS, in a different dataset.
    def shares(flagged: dict[str, set[str]], drop: set[str]) -> dict[str, float]:
        live = {
            axis: 1.0 for axis, pats in flagged.items() if pats - drop
        }
        total = sum(live.values())
        return {axis: v / total for axis, v in live.items()} if total else {}

    base_share_num: dict[str, float] = collections.defaultdict(float)
    n_with_any = 0
    for f in fired:
        sh = shares(f, set())
        if sh:
            n_with_any += 1
            for axis, v in sh.items():
                base_share_num[axis] += v
    base_share = {
        axis: base_share_num[axis] / n_with_any if n_with_any else 0.0 for axis in axes
    }

    pairs: list[dict] = []
    skipped: list[dict] = []
    for row in rows:
        cid = row["id"]
        info = derived.get(cid, {})
        mondo_axes = set(info.get("derived_axes") or [])
        hand_axes = {a.strip() for a in row["organ_axes"].split(";") if a.strip()}
        pinned = row["mondo_id"].strip()
        if not mondo_axes:
            skipped.append({
                "id": cid,
                "reason": "no MONDO-derived axis, so no positive cell to test",
            })
            continue
        at_root = pinned == ROOT_TERM
        matcher = condition_matcher(
            row["label"],
            None if at_root else names.get(pinned),
            set() if at_root else synonyms.get(pinned, set()),
        )
        if matcher is None:
            skipped.append({"id": cid, "reason": "no usable name form"})
            continue
        # The patterns this condition's own name matches. Removing them is what makes the
        # test non-circular; see the module note.
        self_patterns: set[str] = set()
        probe = " ".join(
            [row["label"], names.get(pinned) or ""] + sorted(synonyms.get(pinned, ()))
        )
        for organ, entry in extractor.extract(probe).items():
            self_patterns |= set(entry["patterns"])

        idx = [i for i, text in enumerate(texts) if matcher.search(text)]
        if len(idx) < MIN_TRIALS:
            skipped.append({"id": cid, "reason": f"only {len(idx)} mentioning trials"})
            continue
        if len(idx) > MAX_CORPUS_SHARE * len(trials):
            skipped.append({
                "id": cid,
                "reason": (
                    f"matcher hit {len(idx)} of {len(trials)} trials "
                    f"({100 * len(idx) / len(trials):.0f}%), so it is matching something "
                    "generic rather than this condition"
                ),
            })
            continue
        # Shares for the mentioning trials, with this condition's own patterns removed.
        sh_rows = [shares(fired[i], self_patterns) for i in idx]
        sh_rows = [r for r in sh_rows if r]
        mean_share = {
            axis: (sum(r.get(axis, 0.0) for r in sh_rows) / len(sh_rows))
            if sh_rows else 0.0
            for axis in axes
        }
        for axis in axes:
            n_flag = sum(
                1 for i in idx if (fired[i].get(axis, set()) - self_patterns)
            )
            rate = n_flag / len(idx)
            b = base[axis]
            pairs.append({
                "condition": cid, "axis": axis,
                "n_trials": len(idx), "rate": rate, "base_rate": b,
                "log2_enrichment": (
                    math.log2(rate / b) if rate > 0 and b > 0 else None
                ),
                "share": mean_share[axis],
                "base_share": base_share[axis],
                "log2_share_enrichment": (
                    math.log2(mean_share[axis] / base_share[axis])
                    if mean_share[axis] > 0 and base_share[axis] > 0 else None
                ),
                "in_mondo": axis in mondo_axes,
                "in_hand": axis in hand_axes,
                "self_patterns_removed": sorted(
                    self_patterns & {
                        p for f in fired for ps in [f.get(axis, set())] for p in ps
                    }
                ),
            })

    usable = [p for p in pairs if p["log2_enrichment"] is not None]
    conditions = sorted({p["condition"] for p in pairs})
    print(f"조건 {len(conditions)}개 x 축 {len(axes)}개 = 셀 {len(pairs)}개 "
          f"(그중 농축 계산 가능 {len(usable)})")
    print(f"건너뛴 조건 {len(skipped)}개")

    out: dict = {
        "provenance": stamp({"registry": REGISTRY}),
        "n_trials": len(trials),
        "base_shares": base_share,
        "min_trials_per_condition": MIN_TRIALS,
        "axes": axes,
        "base_rates": base,
        "n_conditions_tested": len(conditions),
        "conditions_tested": conditions,
        "skipped": skipped,
        "pairs": pairs,
    }

    for metric, mlabel in (("log2_share_enrichment", "시험별 점유율 정규화 (주 지표)"),
                           ("log2_enrichment", "원 비율 (상세도 교란 포함)")):
        print(f"\n=== {mlabel} ===")
        rows_m = [p for p in pairs if p[metric] is not None]
        for key, label in (("in_mondo", "MONDO 유도 (비순환)"),
                           ("in_hand", "수작업 (순환 — 대조)")):
            scores = [p[metric] for p in rows_m]
            labels = [int(p[key]) for p in rows_m]
            auc = _auroc(scores, labels)
            pos = sorted(p[metric] for p in rows_m if p[key])
            neg = sorted(p[metric] for p in rows_m if not p[key])
            print(f"  {label}")
            print(f"    양성 {len(pos)}, 음성 {len(neg)}")
            if pos and neg:
                print(f"    중앙값: 지정 {pos[len(pos)//2]:+.3f}  vs  "
                      f"비지정 {neg[len(neg)//2]:+.3f}")
            print(f"    AUROC {auc:.3f}" if auc is not None
                  else "    AUROC 계산 불가")
            perm = permutation_p(pairs, metric, key)
            if perm["p"] is not None:
                print(f"    순열검정 p = {perm['p']:.4f}  "
                      f"(귀무 평균 {perm['null_mean']:.3f}, 95분위 "
                      f"{perm['null_p95']:.3f}, {perm['n_permutations']}회)")
            out.setdefault(metric, {})[key] = {
                "auroc": auc, "n_positive": len(pos), "n_negative": len(neg),
                "median_positive": (pos[len(pos) // 2] if pos else None),
                "median_negative": (neg[len(neg) // 2] if neg else None),
                "permutation": perm,
            }

    print("\n조건별 상위 점유율 농축 축 (MONDO 지정 축에 ★)")
    by_cond: dict[str, list[dict]] = collections.defaultdict(list)
    for p in pairs:
        if p["log2_share_enrichment"] is not None:
            by_cond[p["condition"]].append(p)
    for cid in conditions:
        if not by_cond[cid]:
            continue
        top = sorted(by_cond[cid], key=lambda p: -p["log2_share_enrichment"])[:3]
        shown = ", ".join(
            f"{'★' if p['in_mondo'] else ''}{p['axis']}"
            f"{p['log2_share_enrichment']:+.2f}"
            for p in top
        )
        n = by_cond[cid][0]["n_trials"] if by_cond[cid] else 0
        print(f"  {cid:26s} n={n:5d}  {shown}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
