# Organ labels v5 — execution report (in progress)

Status: Sol pilot reviewed; five labeling passes are running. Adjudication, audit, and assembly are not complete. No DONE marker has been created.

## 1. Models and settings

- Labeling: `gpt-6.1-sol`, reasoning effort `high`, identical across all five planned passes, explicitly selected by the user.
- Selection: OpenAI's official model catalog describes Astra as its most capable general reasoning model; an authenticated fresh Codex CLI call succeeded.
- Transport: fresh, ephemeral `codex exec` sessions through existing ChatGPT authentication. OPENAI_API_KEY was absent. Each session receives the unmodified guide and exactly one batch, with no earlier model responses or other pass labels. No tools are permitted in pass responses.
- Adjudication/audit: planned `gpt-6.1-sol` at maximum supported reasoning; actual setting and usage will be recorded after execution.
- User-facing start date: 2026-10-21 (Asia/Seoul). Per-call timestamps are UTC in runs.jsonl.
- Calls, tokens, and approximate API-equivalent cost: pending completion. Codex subscription billing is not an API invoice; no API key is stored or printed.

## 2. Pilot

The completed Astra pilot contained 300 labels and was reviewed directly. No broad systematic omission of mechanism axes, mouth mapping, or transient-sign exclusion was found. Four rejected calls exceeded the basis character cap; independent retries resolved them. Sparse rare-disease case series and site-unspecified tumors remained close calls. The user then explicitly selected gpt-6.1-sol/high. All Astra outputs were moved to provenance/pilot_astra_out and are excluded from every pass and downstream vote. A fresh Sol pilot is required and running. No Sol call sees Astra outputs.

## 3. Counts

Input concepts: 22,638. Prepared batches per pass: 2,264. Initial pass1 check: 0 done, 2,264 missing, 0 invalid. Final counts pending.

## 4. Agreement

Pending completion of the five independent passes.

## 5. Recurring disagreements

Pending adjudication.

## 6. Audit

Pending. Pass 6 will be run if more than 5% of the random sample requires correction.

## 7. Problems

- The default Python environment lacked NumPy and the OpenAI SDK. Installing globally was denied by filesystem ownership. Both were installed in `/tmp/adctox-v5-venv`; repository scripts were not changed.
- API credentials were absent; the task's explicitly permitted fresh-context fallback is used.
- A transport/validation runner at `/tmp/adctox_v5_fresh.py` invokes a new model context for each batch, validates the raw model response, and persists it verbatim (apart from final newline normalization). It never generates or derives labels by script. Invalid calls are retried in fresh contexts.
- Raw responses, session events, and protected-file hashes are retained under `provenance/`. Model output is accepted only after format and provenance checks.
- Evaluation data has not been opened. Unrelated existing workspace modifications are left untouched.

- Model change: user explicitly requested gpt-6.1-sol/high after the Astra pilot finished. The original pilot is preserved only as excluded provenance. All pass outputs are regenerated independently with Sol.

Sol pilot: all 300 labels were reviewed directly against the guide; no broad systematic errors in the five requested categories were found. Close calls included very small HPO denominators, undefined tumor origin, tier selection and secondary complications. No output was manually corrected. Sol/high is retained as explicitly requested. Full pass dispatch uses up to 256 fresh simultaneous sessions across independently shuffled pass batches, without sharing any responses.
