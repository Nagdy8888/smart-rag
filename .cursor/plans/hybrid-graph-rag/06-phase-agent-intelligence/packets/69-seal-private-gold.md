---
phase: 6
packet: 69
status: pending
title: "Seal private aliases, isolation-slice gold, and the frozen 30-question acceptance sample."
requirement_ids: [P06-69]
---

# Packet 69 — Seal private aliases, isolation-slice gold, and the frozen 30-question acceptance sample.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Load [`.cursor/skills/implement-observability-evals/SKILL.md`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

## Preconditions

- P06-68 live smoke stores diagnostics with zero unknown required
  fields.
- The 100-question Ask gold currently has empty aliases, so grounded
  fact equals strict phrase.
- Hosted `eval_quiz_cases` and `eval_exam_runs` were empty on
  2026-09-21.
- The coding model may draft candidates. A human reviewer must
  approve every alias, chunk ID, and 30-question item. The coding
  model cannot be the gold or semantic reviewer.
- Production remains sample-blind.

## Allowed outputs

- Gitignored private files under `.private-eval/` for aliases, the
  12-question isolation slice, and the frozen 30-question acceptance
  sample.
- Hosted `eval_quiz_cases` rows for the isolation slice, if that table
  is the existing exam-runner contract.
- Count-only evidence in git: item counts, approval statement, no
  questions or gold phrases.
- `.gitignore` entries if `.private-eval/` is not already ignored.
- Evidence files named below.

## Forbidden outputs

- Committing questions, gold phrases, aliases, page numbers, chunk
  IDs, unrestricted PDF excerpts, or expected answers.
- Encoding any of those values in production code, prompts, tests, or
  migrations.
- The coding model marking aliases or the 30-question set approved.
- Opening holdout P06-18.
- Rewriting frozen gold after seeing answers in later packets.

## Ordered actions

1. Confirm `.private-eval/` is gitignored. Add it only if missing.

2. Draft, then wait for human approval of:
   - aliases for the 100-question Ask gold;
   - chunk IDs for a 12-question isolation slice;
   - a 30-question post-merge acceptance sample derived from the
     user-owned PDF, with known answers held privately.

3. Write approved private files only under `.private-eval/`. Do not
   stage them.

4. If using `eval_quiz_cases`, insert the 12-question slice with
   review_status approved by the human, not the model.

5. Freeze the 30-question file. Later packets must not edit questions
   or gold after seeing model answers.

6. Publish count-only evidence.

## Acceptance checks

- Human approval is recorded by name-or-chat-handle and date.
- Private files exist locally and are untracked.
- Git diff of this packet contains no gold phrases, questions, or
  aliases.
- Isolation slice has 12 items. Acceptance sample has 30 items.
- 100-question aliases are non-empty after approval.
- Production files remain sample-blind.

## Negative tests

- Model-only approval without a human statement fails.
- Staging `.private-eval/` or `dataset/*.pdf` fails.
- Empty aliases after this packet fails later grounded-fact
  measurement and must not be marked done.

## Stop routes

- Stop and leave this packet pending if the human has not approved
  aliases, chunk IDs, and the 30-question sample.
- Do not invent gold or mark the packet complete without that
  approval.
- If the user is unavailable, record the blocker in evidence and
  stop. Do not skip to P06-70.

## Required evidence

Create
[`p06-69-seal-private-gold-2026-09-21.md`](../../../../../docs/development/phase-06/p06-69-seal-private-gold-2026-09-21.md)
and append to
[`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):

- Alias count, isolation-slice count, acceptance-sample count.
- Human approver identity (chat handle) and date.
- Proof `.private-eval/` is gitignored and untracked.
- Rollback: delete local private files; do not delete hosted
  documents.

Commands:

```powershell
git check-ignore -v .private-eval
git status --short
git diff --check
```
