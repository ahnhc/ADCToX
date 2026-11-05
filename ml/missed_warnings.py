"""Warnings that never reach the patient. Macro-F1 weighs all 13 organs alike; this counts what a missed organ costs.

evidence maps an organ to (n_boxed, n_wp): how many of the 15 ADC labels carry a Boxed Warning or a Warnings and Precautions
entry on that organ (warning_counts reads ml/data/label_evidence.json). A link is one (question, gold organ, ADC) triple with
a warning, so a question that misses the lung loses one link per ADC that warns on the lung.

    missed_warnings(pred, gold, evidence): pred and gold are aligned lists of organ lists, one entry per valid question;
    a rejected question is an empty prediction.
"""
import json, os

EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "label_evidence.json")


def warning_counts(path=EVIDENCE):
    ev = json.load(open(path, encoding="utf-8"))["evidence"]; out = {}
    for adc in ev.values():
        for organ, v in adc["organs"].items():
            b, w = out.get(organ, (0, 0)); lv = v.get("level") if isinstance(v, dict) else v
            out[organ] = (b + (lv == "boxed"), w + (lv == "W&P"))
    return out


def missed_warnings(pred, gold, evidence):
    assert len(pred) == len(gold)
    boxed = lambda o: evidence.get(o, (0, 0))[0]; wp = lambda o: evidence.get(o, (0, 0))[1]
    bt = bm = wt = wm = qb = silent = 0; tp = {}; fp = {}; fn = {}
    for p, g in zip(pred, gold):
        p, g = set(p), set(g); miss = g - p
        bt += sum(boxed(o) for o in g); bm += sum(boxed(o) for o in miss)
        wt += sum(wp(o) for o in g); wm += sum(wp(o) for o in miss)
        qb += any(boxed(o) for o in miss); silent += bool(p) and bool(miss)
        for o in p | g:
            tp[o] = tp.get(o, 0) + (o in p and o in g); fp[o] = fp.get(o, 0) + (o in p and o not in g); fn[o] = fn.get(o, 0) + (o in g and o not in p)
    warned = [o for o in tp if boxed(o) + wp(o) > 0]
    f1 = [2 * tp[o] / (2 * tp[o] + fp[o] + fn[o]) for o in warned]
    rate = lambda a, b: a / b if b else None
    return dict(n=len(gold), boxed_links=bt, boxed_missed=bm, boxed_miss_rate=rate(bm, bt), wp_links=wt, wp_missed=wm, wp_miss_rate=rate(wm, wt),
                questions_missed_boxed=qb, silent_partial=silent, macro_f1_warned=sum(f1) / len(f1) if f1 else None, organs_warned=len(warned))


def line(r):
    pc = lambda x: "-" if x is None else f"{100 * x:.1f}%"
    f1 = "-" if r["macro_f1_warned"] is None else f"{r['macro_f1_warned']:.3f}"
    return (f"n {r['n']}  Boxed missed {r['boxed_missed']}/{r['boxed_links']} ({pc(r['boxed_miss_rate'])})  W&P missed {r['wp_missed']}/{r['wp_links']} "
            f"({pc(r['wp_miss_rate'])})  questions missing a Boxed organ {r['questions_missed_boxed']}  silent partial {r['silent_partial']}  "
            f"macro-F1 over {r['organs_warned']} warned organs {f1}")
