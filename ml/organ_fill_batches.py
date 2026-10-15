"""Batches for the third concept-organ round (Haiku 5.5, GUIDE.md 'v3 additions'): every human MONDO concept of the index
that has no label yet, plus labelled concepts whose label is 'no organ' (re-judged under the v3 rules).

    python ml/organ_fill_batches.py [N_BATCHES]   -> data/curated/concept_organs/batches/v4_*.txt, fill_manifest.json

Gold concepts and their parents and children are left out. Each batch carries 5 calibration concepts from the gold.
"""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ADC_RESEARCH_MODE", "1")
import numpy as np
import linking_models as LM, suggest as SG
from build_linking_pools import read_obo
from sample_label_concepts import line, held_out

R = LM.R + "concept_organs/"


def main(n_batches=100):
    rng = random.Random(77); T = read_obo(); held, _ = held_out(T); labels, _ = LM.load_organ_labels()
    d = np.load(LM.C + "mondo_index.npz", allow_pickle=True); nh = SG.nonhuman_ids(LM.MONDO_OBO)
    concepts = [t for t in dict.fromkeys(str(x) for x in d["ids"]) if t in T and t not in nh and t not in held and not T[t]["name"].startswith("obsolete")]
    todo = [t for t in concepts if t not in labels] + [t for t in concepts if t in labels and not labels[t]]
    rng.shuffle(todo); cal = sorted(json.load(open(R + "manifest.json"))["calibration"]); out = {}
    for k in range(n_batches):
        b = todo[k::n_batches] + cal[(k * 5) % len(cal):(k * 5) % len(cal) + 5]; rng.shuffle(b); out[f"v4_{k:02d}"] = b
        open(R + f"batches/v4_{k:02d}.txt", "w", encoding="utf-8").write("\n".join(line(T, t) for t in b) + "\n")
    json.dump(dict(todo=todo, relabel_no_axis=[t for t in todo if t in labels], batches=out), open(R + "fill_manifest.json", "w"), indent=0)
    print(f"{len(todo)} concepts ({sum(t in labels for t in todo)} re-judged 'no organ'), {n_batches} batches of ~{len(todo) // n_batches}+5")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
