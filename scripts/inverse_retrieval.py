"""Does the system propose an approved ADC's own design when given only its target?

The plan calls this the most important evaluation, and the reason is that it is the only
one that tests the *product* rather than a component. Everything else scores a predicted
rate; this asks whether the proposal path, given a target antigen and a patient profile,
puts the molecule that actually exists near the top of its list.

Four confounds, three of them fatal if ignored, and the plan names all four.

**The forward model has seen the drug.** Its pivotal trials are in the corpus, so a model
asked to rank designs for HER2 already knows what DM1 on a non-cleavable linker does to a
HER2 population. Every agent is therefore held out of the fit before its own retrieval is
scored -- which is why this costs fifteen refits and not one.

**The precedent objective can short-circuit the test.** O3 rewards configurations that
clinical ADCs already use, and the held-out agent contributes to those counts. Its
components' counts are decremented before scoring, and the test is run both ways: the gap
between them is the share of any success that is precedent memorisation rather than
prediction, and the plan is right that the gap is more interesting than the headline.

**The profile must not come from exclusion criteria.** Those feed the exclusion head, so a
profile built from them would be scored against a model that already encodes them. The
profile is built from the label's Use in Specific Populations section instead.

**Target duplication.** Two agents share HER2 and two share TROP2 among the approved set,
so fifteen agents are nearer eleven independent target-design pairs. Reported, not
corrected away.

What this does not do is claim design capability. The honest headline is slot-level
accuracy against the chance rate for the *feasible* candidate set -- computed here rather
than taken from nominal slot counts, because chance depends on what the enumerator can
actually build for that target.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from adctox.provenance import stamp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "conf" / "adc_registry.yaml"

# A slot whose chance rate in the feasible set exceeds this is not worth scoring: matching
# it says almost nothing. Measured on the HER2 candidate set, isotype matches 89% of
# feasible designs and masking 91%, because IgG1 and no-masking dominate what the
# enumerator can build. Counting those as hits is how "4 of 6 slots, chance 2.03" would be
# reported for a result carrying two informative matches. The threshold is applied per
# agent, since the feasible set differs by target.
UNINFORMATIVE_CHANCE = 0.5

# Below this many posterior draws the fit is a smoke test, not an evaluation, and the
# artefact says so in a field rather than only in a log line. A two-agent run at 80 draws
# reported "informative slots 1/7, chance 1.30, excess -0.30, p 0.77" -- a number that
# looks like a finding and is a statement about an unconverged sampler.
MIN_DRAWS_FOR_A_RESULT = 300

# Slots scored. `mechanism` and `cleavable` are functions of `payload` and `linker`, so
# scoring them would double-count; `target` is the input. Fc engineering is not a slot --
# the project dropped it as a lever after finding no approved ADC uses it.
SLOTS = ("payload", "linker", "conjugation", "dar", "isotype", "masking")

# The label guidance level that makes a comorbidity worth putting in the profile. "Avoid"
# and "not established" are the label restricting use; "monitor" is weaker but still a
# statement about that organ. "No adjustment" is the label saying the organ is fine, so it
# contributes nothing.
PROFILE_LEVELS = {"avoid", "not_established", "monitor"}
# Which registry condition stands for impairment of each organ. Deliberately the moderate
# rather than the severe form: a label that says "avoid severe renal impairment" is
# describing a population the trial would have excluded outright, and the product is asked
# about patients who might plausibly be treated.
ORGAN_TO_CONDITION = {"hepatic": "chronic_liver_disease", "renal": "ckd_stage_3"}


def label_profile(agent: str, impairment: dict) -> list[str]:
    """Conditions for this agent, from its label's impairment guidance."""
    out: list[str] = []
    for cell in impairment.get("cells", []):
        if cell["agent"] != agent or cell["level"] not in PROFILE_LEVELS:
            continue
        cond = ORGAN_TO_CONDITION.get(cell["organ"])
        if cond and cond not in out:
            out.append(cond)
    return out


def decremented_design_space(spec: dict) -> dict:
    """`design_space.yaml` with the held-out agent's own contribution removed.

    One count per component, because one agent is one ADC. Without this the precedent
    objective rewards exactly the configuration being searched for, and a hit would not
    distinguish prediction from memory.
    """
    doc = yaml.safe_load((ROOT / "conf" / "design_space.yaml").read_text(encoding="utf-8"))
    for section, key in (
        ("payloads", spec.get("payload")),
        ("linkers", spec.get("linker_type")),
        ("conjugation_dar", spec.get("conjugation")),
    ):
        entry = doc.get(section, {}).get(key)
        if isinstance(entry, dict):
            for field in ("clinical_adcs", "approved_adcs"):
                if field in entry:
                    entry[field] = max(0, int(entry[field]) - 1)
    return doc


def slot_matches(proposed: dict, spec: dict) -> dict[str, bool]:
    truth = {
        "payload": spec.get("payload"),
        "linker": spec.get("linker_type"),
        "conjugation": spec.get("conjugation"),
        "dar": spec.get("dar"),
        "isotype": spec.get("isotype"),
        "masking": "none",
    }
    out: dict[str, bool] = {}
    for slot in SLOTS:
        got, want = proposed.get(slot), truth.get(slot)
        if want is None:
            out[slot] = False
        elif slot == "dar":
            out[slot] = got is not None and abs(float(got) - float(want)) <= 0.25
        else:
            out[slot] = got == want
    return out


def chance_rate(candidates: list[dict], spec: dict) -> dict[str, float]:
    """Per-slot probability that a candidate drawn at random from the feasible set matches.

    Computed from the enumerated set rather than from nominal slot counts, because the
    enumerator's chemistry constraints make the slots dependent -- a payload admits one to
    three linkers -- and a nominal 1/11 would understate chance badly.
    """
    if not candidates:
        return {slot: 0.0 for slot in SLOTS}
    hits = collections.Counter()
    for cand in candidates:
        for slot, ok in slot_matches(cand, spec).items():
            hits[slot] += ok
    return {slot: hits[slot] / len(candidates) for slot in SLOTS}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", type=pathlib.Path,
                    default=ROOT / "data" / "processed")
    ap.add_argument("--impairment", type=pathlib.Path,
                    default=ROOT / "artifacts" / "label_impairment_eval.json")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "artifacts" / "inverse_retrieval.json")
    ap.add_argument("--agents", default=None,
                    help="comma-separated subset, for a bounded run")
    ap.add_argument("--warmup", type=int, default=400)
    ap.add_argument("--samples", type=int, default=400)
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20261009)
    args = ap.parse_args()

    import adctox.model.dataset as ds
    from adctox.model.predict import Posterior
    from adctox.pipeline import propose
    from adctox.taxonomy import default_taxonomy
    from numpyro.infer import MCMC, NUTS
    import jax
    from adctox.model import forward

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["agents"]
    impairment = (
        json.loads(args.impairment.read_text(encoding="utf-8"))
        if args.impairment.exists() else {"cells": []}
    )
    axes = list(default_taxonomy().axis_order)
    full = ds.load(args.processed, axes, kind="other")

    wanted = (
        [a.strip() for a in args.agents.split(",")] if args.agents
        else [a for a in full.agents if registry.get(a, {}).get("first_us_approval")]
    )
    wanted = [a for a in wanted if a in full.agents]
    print(f"역방향 검증 대상 {len(wanted)}종 (코퍼스 {len(full.agents)}종)")
    targets = collections.Counter(registry[a]["target"] for a in wanted)
    dup = {t: n for t, n in targets.items() if n > 1}
    print(f"  표적 중복: {dup or '없음'} → 유효 N 약 {len(set(targets))}")

    results: list[dict] = []
    for i, agent in enumerate(wanted, 1):
        spec = registry[agent]
        # The agent and every trial it shared go out of the fit; see
        # dataset.build's `drop_agents` and tests/test_agent_holdout.py.
        held = ds.load(args.processed, axes, kind="other", drop_agents=[agent])
        t0 = time.time()
        kernel = NUTS(forward.model)
        mcmc = MCMC(kernel, num_warmup=args.warmup, num_samples=args.samples,
                    num_chains=1, progress_bar=False)
        mcmc.run(jax.random.PRNGKey(args.seed + i), data=held)
        post = Posterior.from_samples(mcmc.get_samples(), held)
        fit_s = time.time() - t0

        profile = label_profile(agent, impairment)
        row: dict = {
            "agent": agent, "target": spec["target"], "profile": profile,
            "fit_seconds": round(fit_s, 1),
            "held_out_corpus": held.summary(),
        }
        for tag, decrement in (("with_precedent", False), ("precedent_adjusted", True)):
            # One call with a large `top_k` so the whole feasible set comes back: the
            # chance rate has to be computed over everything the enumerator could have
            # built for this target, not over the six that were returned. Scoring then
            # uses the first `--top-k` of the same ranked list.
            proposal = propose(
                spec["target"], profile, post, top_k=10_000,
                hard_flags=False,
                design_space_override=(
                    decremented_design_space(spec) if decrement else None
                ),
            )
            feasible = [c["design"] for c in proposal["candidates"]]
            cands = feasible[: args.top_k]
            per_slot = [slot_matches(c, spec) for c in cands]
            best = max(
                (sum(m.values()) for m in per_slot), default=0
            )
            top1 = sum(per_slot[0].values()) if per_slot else 0
            chance = chance_rate(feasible, spec)
            informative = [s_ for s_ in SLOTS if chance[s_] < UNINFORMATIVE_CHANCE]
            top1_slots = per_slot[0] if per_slot else {}
            row[tag] = {
                "n_candidates": len(cands),
                # The honest headline. Slots the feasible set nearly fixes are excluded,
                # and the chance expectation is the sum of per-slot chance over the same
                # subset rather than a nominal count.
                "informative_slots": informative,
                "informative_matched_top1": sum(
                    bool(top1_slots.get(s_)) for s_ in informative
                ),
                "informative_chance_expected": round(
                    sum(chance[s_] for s_ in informative), 3
                ),
                "uninformative_slots": [
                    s_ for s_ in SLOTS if chance[s_] >= UNINFORMATIVE_CHANCE
                ],
                "slots_matched_top1": top1,
                "slots_matched_best_of_k": best,
                "exact_in_top_k": any(all(m.values()) for m in per_slot),
                "per_slot_top1": per_slot[0] if per_slot else {},
                "n_feasible": len(feasible),
                "chance": chance,
                "all_slots_chance_expected": round(sum(chance.values()), 3),
            }
        wp = row["with_precedent"]
        pa = row["precedent_adjusted"]
        print(f"  [{i}/{len(wanted)}] {agent:28s} "
              f"정보슬롯 {wp['informative_matched_top1']}/"
              f"{len(wp['informative_slots'])} "
              f"(우연 {wp['informative_chance_expected']:.2f}) "
              f"| 선례조정 {pa['informative_matched_top1']} "
              f"| 전체 {wp['slots_matched_top1']}/{len(SLOTS)} "
              f"| {fit_s:.0f}s", flush=True)
        results.append(row)

    summary: dict = {}
    for tag in ("with_precedent", "precedent_adjusted"):
        got = sum(r[tag]["informative_matched_top1"] for r in results)
        exp = sum(r[tag]["informative_chance_expected"] for r in results)
        n_slots = sum(len(r[tag]["informative_slots"]) for r in results)
        # Paired permutation over the binary slot outcomes, which respects that the slots
        # of one agent come from one ranked list.
        rng = random.Random(args.seed)
        obs = got - exp
        ge = 0
        trials_n = 2000
        for _ in range(trials_n):
            draw = 0.0
            for r in results:
                for s_ in r[tag]["informative_slots"]:
                    draw += rng.random() < r[tag]["chance"][s_]
            ge += (draw - exp) >= obs
        summary[tag] = {
            "informative_slots_total": n_slots,
            "matched": got,
            "chance_expected": round(exp, 2),
            "excess": round(obs, 2),
            "permutation_p": (ge + 1) / (trials_n + 1),
        }
        print(f"\n{tag}: 정보 슬롯 {got}/{n_slots} 일치, 우연 기대 {exp:.2f}, "
              f"초과 {obs:+.2f}, 순열 p {summary[tag]['permutation_p']:.4f}")
    gap = (summary["with_precedent"]["matched"]
           - summary["precedent_adjusted"]["matched"])
    print(f"선례 암기의 몫: {gap} 슬롯 "
          "(선례 포함 − 선례 조정; 계획서는 이 차이가 대표 숫자보다 흥미롭다고 했습니다)")

    is_result = (
        args.samples >= MIN_DRAWS_FOR_A_RESULT
        and args.warmup >= MIN_DRAWS_FOR_A_RESULT
        and args.agents is None
    )
    if not is_result:
        print(
            "\n*** 이 실행은 결과가 아닙니다 ***\n"
            f"    draws {args.warmup}/{args.samples} "
            f"(결과 기준 {MIN_DRAWS_FOR_A_RESULT} 이상), "
            f"대상 {'부분집합' if args.agents else '전체'}.\n"
            "    하네스가 계산한다는 것만 확인하며, 위 수치는 인용 대상이 아닙니다."
        )

    out = {
        "provenance": stamp({"registry": REGISTRY}),
        "is_result": is_result,
        "why_not_a_result": (
            None if is_result else
            f"warmup/samples {args.warmup}/{args.samples} below "
            f"{MIN_DRAWS_FOR_A_RESULT}, or an agent subset was named; the posterior is "
            "not converged and the aggregate is a wiring check"
        ),
        "warmup": args.warmup,
        "samples": args.samples,
        "slots": list(SLOTS),
        "uninformative_chance_threshold": UNINFORMATIVE_CHANCE,
        "summary": summary,
        "precedent_memorisation_slots": gap,
        "n_agents": len(results),
        "distinct_targets": len(set(r["target"] for r in results)),
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
