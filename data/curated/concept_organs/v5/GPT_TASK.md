# Task: organ labels v5 for 22,638 disease concepts (ChatGPT subscription, Codex)

You are working in the ADCTOX repository. Run every command from its root. Your job is to produce the most accurate organ labels
possible for 22,638 MONDO disease concepts, following `data/curated/concept_organs/GUIDE_v5.md`. Accuracy matters more than time.
The work runs through `codex exec` on the user's ChatGPT subscription. There is no API key, so it must stay within the
subscription's rate limits. A separate system imports the result, so follow the file layout exactly.

**Worker model:** every labelling, adjudication and audit call uses `gpt-6.1-sol` with reasoning effort `high`. These are the
defaults of `ml/relabel_v5_codex.py`. Do not change them.

Paths below are relative to `data/curated/concept_organs/v5/` unless they start with `ml/` or `data/`.
Use this Python for every command: `PY=/data/hyeongchanahn/envs/adctox/bin/python` (it has the needed packages), with
`ADC_RESEARCH_MODE=1` set.

## What went wrong in the first attempt (do not repeat it)

- A runner in `/tmp/adctox_v5_fresh.py` opened up to 256 `codex exec` sessions at once. The subscription answered `429 Too Many Requests`, then Cloudflare `403 Forbidden`.
- 72% of the calls were rejected because the model used a tool to read its batch file.

The new runner fixes both:
- It runs at most a few sessions at a time.
- It pauses everything when a limit is hit.
- It runs every call in its own empty folder holding only the instructions and that batch, so tool use there is harmless and allowed.

Never start more than 4 `codex exec` sessions at once, and never write your own runner.

## Rules you must keep

1. **Independence.** The passes are independent opinions. Each batch of each pass is answered by a fresh session that sees only the instructions and that batch; the runner does this. Never show a session another pass's output, the older labels, or earlier answers. Never copy, merge or fix one pass from another.
2. **No invented outputs.** Every output line comes from a model session that read the batch. Never write outputs by script, by rule, from the older labels, or by hand.
3. **Do not edit the rules or the inputs.** If a rule seems wrong, keep following it and write it in `REPORT.md`.
   - Do not edit `GUIDE_v5.md`, `ADJUDICATE.md`, `AUDIT.md`, `input/` or `*/in/`.
   - Do not edit the `ml/relabel_v5*.py` scripts, except to fix a bug that stops them. Describe any such fix in `REPORT.md`.
4. **Stay out of the evaluation data.** Do not open `data/curated/disease_linking/`, `data/curated/known_eval/`, `data/curated/judge2/gen/koeval_*`, `ml/results/` or `ml/docs/`. Do not try to find out which concepts are used for evaluation.

## Steps

### 0. Stop the first attempt

Stop the old runner and the `codex exec` sessions it started. Touch nothing else:
- stop the `/tmp/adctox_v5_fresh.py` process;
- stop every `codex exec ... --ephemeral ... -m gpt-6.1-sol` process.

Do not stop the `codex app-server` processes or your own session. Confirm none is left:

```bash
pgrep -fc "adctox_v5_fresh|codex exec"
```

### 1. Rebuild the batches (3 passes × 25 concepts)

```bash
ADC_RESEARCH_MODE=1 $PY ml/relabel_v5.py prepare --passes 3 --batch 25
```

The old layout (5 passes of 10, including the finished batches of the first attempt) moves to `provenance/old_layout_<time>/`.
It is kept but never used. The manifest should report 22,638 concepts, 3 passes and 906 batches per pass.

### 2. Pilot

```bash
ADC_RESEARCH_MODE=1 $PY ml/relabel_v5_codex.py --stage pass1 --limit 4
```

Read the 100 labels in `pass1/out/b_0000.jsonl` … `b_0003.jsonl` yourself against `GUIDE_v5.md`. Look for:
- organs added from complications under 30%;
- missing mechanism axes (`infectious_immune`, `metabolic_endocrine`, `haematologic`);
- mouth not labelled `gastrointestinal`;
- transient signs counted as organs;
- empty or long `basis`.

Write what you saw in `REPORT.md`. Do not edit the labels.

### 3. The three passes

Run in the background so it survives your turn ending, and watch the log:

```bash
ADC_RESEARCH_MODE=1 nohup $PY ml/relabel_v5_codex.py --stage all --workers 3 > provenance/codex_passes.log 2>&1 &
tail -f provenance/codex_passes.log
```

- When a limit is hit, the runner pauses every worker for 15, 30, then 60 minutes and goes on by itself. This is expected on a subscription. Do not restart it in a loop or add workers.
- If the log shows limit pauses more often than about once an hour, stop it and restart with `--workers 2`.
- If it stops for another reason, start the same command again. Finished batches are skipped.
- Expect about 2,700 sessions for this step, and days rather than hours of wall time.

When it finishes, check every pass and re-run until each reports 0 missing and 0 invalid:

```bash
for k in 1 2 3; do ADC_RESEARCH_MODE=1 $PY ml/relabel_v5.py check --stage pass$k; done
```

### 4. Vote

```bash
ADC_RESEARCH_MODE=1 $PY ml/relabel_v5.py vote
```

With three passes, an organ's tier is settled only when all three agree, and a concept is settled when all 13 organs and
`no_axis` are. Every other concept goes to `adjudicate/in/` (10 per batch) with the three labels and the older label.

### 5. Adjudication

```bash
ADC_RESEARCH_MODE=1 nohup $PY ml/relabel_v5_codex.py --stage adjudicate --workers 3 > provenance/codex_adjudicate.log 2>&1 &
```

Check it the same way (`check --stage adjudicate`).

### 6. Audit

```bash
ADC_RESEARCH_MODE=1 $PY ml/relabel_v5.py audit
ADC_RESEARCH_MODE=1 nohup $PY ml/relabel_v5_codex.py --stage audit --workers 3 > provenance/codex_audit.log 2>&1 &
```

Check it with `check --stage audit`. If more than 5% of the **random sample** gets corrected, report it in `REPORT.md` and
stop there. Do not add passes on your own.

### 7. Assemble and report

```bash
ADC_RESEARCH_MODE=1 $PY ml/relabel_v5.py assemble
```

This writes `labels_v5.jsonl` (22,638 lines), `agreement.json` and `DONE`. Then rewrite `REPORT.md` with these sections:

1. **Models and settings:** model, effort, transport (`codex-exec-isolated-dir`), dates, number of sessions, limit pauses (from `runs.jsonl` and the logs).
2. **First attempt:** what happened and that its outputs are not used.
3. **Pilot:** what you saw.
4. **Counts:** settled by agreement, adjudicated, audit-corrected; `no_axis` count.
5. **Agreement:** per organ, from `agreement.json`, with one sentence on the weakest organs.
6. **Recurring disagreements:** the 10 most common reasons in adjudication `decisions`, each with 2 example concept ids.
7. **Audit:** corrections by flag, and the random-sample correction rate.
8. **Problems:** any rule that seemed wrong, any script fix, any deviation from these steps.

### 8. Finish

Confirm that `DONE`, `labels_v5.jsonl`, `agreement.json` and `REPORT.md` exist. Then tell the user, in Korean, that the v5
labelling is finished and where `REPORT.md` is.

If you must stop before the end (for example the subscription stays limited for a long time), write the current state and the
exact command to resume in `REPORT.md`, and tell the user.
