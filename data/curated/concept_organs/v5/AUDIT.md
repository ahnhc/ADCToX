# Organ labels v5: audit instructions

You audit final organ labels for errors. The rules are in `data/curated/concept_organs/GUIDE_v5.md`; they are binding. Read
them first. Be a strict reviewer: your job is to find the label that a careful internist would not sign.

## Input (`audit/in/u_NNNN.json`)

A list of items, each with:
- `record`: the evidence for the concept.
- `label`: its current final label.
- `flags`: why it was picked. The flags are only reasons to look closely, not findings:
  - the label lacks a defining organ of its parent;
  - it differs from an older label by two or more organs;
  - its confidence is low;
  - random sample.

## What to do

Check each organ of the label against the rules: the tier, and any organ missing or wrongly added. A subtype usually keeps its
parent's defining organs, but not when the subtype is defined by a different organ. Then decide:
- `ok` when the label follows the rules;
- `corrected` when it does not.

## Output (`audit/out/u_NNNN.jsonl`)

One JSON object per item, in input order:

```json
{"id": "MONDO:...", "verdict": "ok", "reason": "..."}
{"id": "MONDO:...", "verdict": "corrected", "reason": "...", "corrected": {"primary": [...], "involved": [...], "no_axis": false, "confidence": "high", "basis": "..."}}
```

`reason`: at most 300 characters. For a correction, name each changed organ and the rule.
