#!/usr/bin/env python
"""How much work does the label-rule layer actually do?

The rules are label-derived overrides that can only raise a band. They are a liability if
they are doing the model's job: a rule encoding "prior ILD plus a deruxtecan payload is
high risk" decides the very question the ILD case study asks, which makes that case study
circular. So the marginal contribution of each rule is measured, not assumed.

For each flag: the serious-event rate the model predicts for that (mechanism, axis), the
band that rate produces on its own, and the band after the rule is applied. A rule that
changes nothing is confirmatory and the model stands alone there. A rule that changes the
band is load-bearing, and the case it covers cannot be claimed as a model result.

Each flag is asserted to actually apply to its own declared comorbidities before being
scored -- an earlier hand-run of this check passed the wrong condition ids and reported
two rules as confirmatory when they had simply not fired.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adctox.comorbidity.hard_flags import applicable, override_band  # noqa: E402
from adctox.model.predict import Posterior, predict_draws, risk_band  # noqa: E402

CONF = Path(__file__).resolve().parents[1] / "conf"

# Payload -> family, needed because prediction takes a family. Read from the registry so
# this cannot drift from the fitted corpus.
def _family_of(registry: dict) -> dict[str, str]:
    out = {}
    for spec in registry.values():
        if spec.get("payload") and spec.get("payload_family"):
            out[spec["payload"]] = spec["payload_family"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    ap.add_argument("--dar", type=float, default=4.0)
    args = ap.parse_args()

    path = args.out / "posterior_serious.npz"
    if not path.exists():
        print(f"{path} absent; build it with `scripts/propose_demo.py --kind serious "
              f"--fit-only`. The flags guard serious-harm axes, so the common table is "
              f"the wrong scale to judge them on.")
        return 1
    post = Posterior.load(path)
    registry = yaml.safe_load(
        (CONF / "adc_registry.yaml").read_text(encoding="utf-8")
    )["agents"]
    fam = _family_of(registry)
    flags = yaml.safe_load((CONF / "hard_flags.yaml").read_text(encoding="utf-8"))["flags"]

    print("Label-rule necessity, judged on the serious-event table\n")
    print(f"  band edges {post.band_edges[0]:.4f} / {post.band_edges[1]:.4f}\n")
    print(f"  {'flag':32s} {'rate':>8s} {'model':>9s} {'+rule':>9s}  verdict")
    rows, load_bearing = [], 0
    for f in flags:
        mech, payload, axis = f["mechanisms"][0], f["payloads"][0], f["axis"]
        if payload not in fam:
            print(f"  {f['id']:32s} payload {payload!r} absent from the registry -- skipped")
            continue
        if mech not in post.mechanisms or axis not in post.axes:
            print(f"  {f['id']:32s} ({mech}, {axis}) not in the corpus -- skipped")
            continue
        applied = applicable(mech, payload, set(f["comorbidities"]), enabled=True).get(axis)
        if not applied:
            raise SystemExit(
                f"{f['id']} does not apply to its own declared comorbidities "
                f"{f['comorbidities']}. Either the flag or hard_flags.applicable is wrong; "
                "this check cannot report on a rule that never fires."
            )
        draws = predict_draws(
            post, mechanisms=[mech], families=[fam[payload]],
            dars=np.array([args.dar]),
            cleavables=np.array([float(f.get("cleavable", 1.0))]),
        )
        j, mi = post.axes.index(axis), post.mechanisms.index(mech)
        rate = float(draws[:, 0, j].mean())
        arms = int(post.evidence_arms[mi, j])
        base = risk_band(rate, arms, post.band_edges)
        after = override_band(base, applied)
        changed = base != after
        load_bearing += changed
        verdict = f"LOAD-BEARING {base} -> {after}" if changed else "confirmatory"
        print(f"  {f['id']:32s} {rate:8.4f} {base:>9s} {after:>9s}  {verdict}")
        rows.append({
            "flag": f["id"], "mechanism": mech, "payload": payload, "axis": axis,
            "serious_rate": rate, "n_arms": arms,
            "band_model_alone": base, "band_with_rule": after,
            "rule_is_load_bearing": changed,
            "source_label": f.get("source_label"),
            "source_section": f.get("source_section"),
        })

    print(f"\n  the rule layer is load-bearing for {load_bearing} of {len(rows)} flags")
    confirmatory = [r["flag"] for r in rows if not r["rule_is_load_bearing"]]
    if confirmatory:
        print(
            f"  confirmatory, so the model stands alone on these: {', '.join(confirmatory)}"
        )
    # The pattern in what the rules still have to carry.
    carried = [r for r in rows if r["rule_is_load_bearing"]]
    within = [r for r in carried
              if sum(1 for q in carried if q["mechanism"] == r["mechanism"]) > 1
              or any(q["mechanism"] == r["mechanism"] and q["payload"] != r["payload"]
                     for q in rows)]
    if within:
        print(
            "\n  Note what the rules carry: "
            + ", ".join(f"{r['payload']}/{r['axis']}" for r in within)
            + ". These are payload-specific effects inside a single mechanism, which is "
            "exactly the resolution this corpus cannot identify -- the mechanism level is "
            "too coarse and the family level does not converge. The rule layer is not "
            "patching a bug; it is covering a structural limit measured three other ways "
            "in this report."
        )

    doc = {
        "band_edges": [float(x) for x in post.band_edges],
        "dar_used": args.dar,
        "n_flags": len(rows),
        "n_load_bearing": load_bearing,
        "n_confirmatory": len(rows) - load_bearing,
        "flags": rows,
    }
    out = args.out / "hard_flag_necessity.json"
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
