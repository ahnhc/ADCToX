# Organ labels v5: adjudication instructions

You settle organ labels on which five independent labellers did not agree. The labelling rules are in
`data/curated/concept_organs/GUIDE_v5.md`; they are binding. Read them first.

## Input (`adjudicate/in/a_NNNN.json`)

A list of items, each with:
- `record`: the evidence for the concept (as the labellers saw it).
- `labels`: the five independent labels, each with `primary`, `involved`, `no_axis`, `confidence` and `basis`.
- `contested_organs`: the organs whose tier (primary / involved / none) fewer than four labellers agreed on.
- `older_label`: the organ set from an older label round (v4). Those rules did not separate primary from involved, and they sometimes added organs from minority complications. Treat it as one more opinion, not as the answer.

## What to do

For every item:
1. Decide every contested organ from the rules and the evidence. Do not count votes: a single labeller can be right.
2. Check the uncontested organs too. If all labellers missed a clear rule (an organ only reached through a separate disease, a treatment effect, a transient sign), correct it.
3. For a 30% call, use the HPO frequencies when present. Otherwise use what you know of the disease's usual course. Write down the frequency you rely on.

## Output (`adjudicate/out/a_NNNN.jsonl`)

One JSON object per item, in input order: the label schema of `GUIDE_v5.md` plus `decisions`.

```json
{"id": "MONDO:...", "primary": [...], "involved": [...], "no_axis": false, "confidence": "high", "basis": "...",
 "decisions": {"ocular": "involved: lens dislocation is a major diagnostic criterion", "neurologic": "none: neuropathy in ~10%"}}
```

`decisions` has one entry per contested organ, at most 200 characters each.
