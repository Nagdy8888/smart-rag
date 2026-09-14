---
title: P06-33 Ask Save to quiz beside thumbs
owner: engineering-lead
status: draft
last-reviewed: 2026-09-13
audience: engineering, reviewers, frontend, security
---

# P06-33 — Add owner/admin Save to quiz beside existing thumbs (2026-09-13)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: add owner/admin Save to quiz beside existing thumbs feedback.

User directed continuous execution through P06-36. This packet does not
modify Admin Evaluation.

## Plan requirement

Quote: add owner/admin Save to quiz beside existing thumbs feedback.

Positive checks: member/viewer keep Give feedback and hide Save to quiz;
owner/admin with capability show both; capability off is feedback only;
zero-gold draft save; XSS remains text; keyboard, focus return, labels,
pending, success, retry, and error states.

Negative checks: newly saved draft cannot score its creating run as quality;
expected answer is not sent to Ask or compare; forged member POST still 403s.

## Files

- [save-to-quiz-popover.tsx](../../../apps/frontend/src/components/chat/save-to-quiz-popover.tsx)
- [use-quiz-capture.ts](../../../apps/frontend/src/components/chat/hooks/use-quiz-capture.ts)
- [chat-app.tsx](../../../apps/frontend/src/components/chat/chat-app.tsx)
- [chat-stage.tsx](../../../apps/frontend/src/components/chat/chat-stage.tsx)
- [pdf-eval.ts](../../../apps/frontend/src/lib/api/pdf-eval.ts)
- [eval-workspace.ts](../../../apps/frontend/src/lib/eval-workspace.ts)
- [action-inventory.json](../../frontend/action-inventory.json)
- [PDF_EVAL_WORKSPACE.md](../../evaluation/PDF_EVAL_WORKSPACE.md)

`FeedbackPopover` and `submitFeedback` remain. Save to quiz is a separate
popover. Admin Evaluation was not edited.

## Verification

| Command | Exit |
| --- | --- |
| `pnpm test --` eval-workspace, api, save-to-quiz, feedback, chat-app, evaluation-panel | 0; 128 passed |
| `pnpm typecheck` | 0 |
| `pnpm lint` | 0 |
| `pnpm build` | 0 |
| `uv run python scripts/check_frontend_action_inventory.py` | 0 |

Create posts `{ source_run_id, query_class, split=development, chunk_ids,
idempotency_key }` and never `question`. Compare posts `{ run_id }` only.

## Proven

- Member/viewer with capability: Give feedback present, Save to quiz absent.
- Owner with capability: both controls. Owner with capability off: feedback only.
- Zero-gold Save draft is allowed. A fourth citation checkbox is disabled with
  an accessible status.
- Hostile query-class strings render through `UserText`. No `script` nodes.
- Newly saved draft IDs are tracked per run and cannot score that run.
- Member `POST /admin/pdf-eval/cases` throws `forbidden`.

## Unverified

- Live Ask create against hosted quiz RPCs (HTTP tests use fetch fakes).
- Admin gold picker (P06-34). Recall@10 scoreboard (P06-35).
- Managed region/DPA/backup matrix rows. Residual-risk exception from P06-27
  still applies.

## Handoff

Next packet is
[P06-34](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/34-admin-eval-curation.md)
(Admin case review, gold picker, stale repair, regenerate). Switch the
frontend off `expected_revision` to `expected_row_version`. Do not add the
exam scoreboard. Do not start P06-11 until P06-36 closes.
