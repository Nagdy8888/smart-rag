---
title: P06-34 Admin case review, gold picker, stale repair, regenerate
owner: engineering-lead
status: draft
last-reviewed: 2026-09-13
audience: engineering, reviewers, frontend, security
---

# P06-34 — Implement Admin case review, gold picker, stale repair, and draft regeneration (2026-09-13)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: implement Admin case review, gold picker, stale repair, and
draft regeneration.

User directed continuous execution through P06-36. This packet does not
add exam start or scoreboard UI.

## Plan requirement

Quote: implement Admin case review, gold picker, stale repair, and draft
regeneration.

Positive checks: first 20 plus pagination to 60; filters and
empty/loading/error/403; gold 0–3 including chunks that were not citations;
edit/gold change clears approval; stale gold blocks approve; hostile
strings and RTL text render safely; keyboard-only picker.

Negative checks: members have no tab; direct API remains 403; stale row
reload on 409; delete confirmation returns focus; regenerate
pending/success/409/error.

## Files

- [evaluation-panel.tsx](../../../apps/frontend/src/components/evaluation/evaluation-panel.tsx)
- [evaluation-gold-picker.tsx](../../../apps/frontend/src/components/evaluation/evaluation-gold-picker.tsx)
- [pdf-eval.ts](../../../apps/frontend/src/lib/api/pdf-eval.ts)
- [eval-workspace.ts](../../../apps/frontend/src/lib/eval-workspace.ts)
- [pdf_eval.py](../../../apps/backend/src/smart_rag_api/routers/pdf_eval.py)
- [action-inventory.json](../../frontend/action-inventory.json)
- [PDF_EVAL_WORKSPACE.md](../../evaluation/PDF_EVAL_WORKSPACE.md)

Frontend mutations send `expected_row_version`. `expected_revision` is
gone from the Admin editor. Exam start/scoreboard stays in P06-35.

## Verification

| Command | Exit |
| --- | --- |
| `pnpm test --` evaluation, pdf-eval, eval-workspace | 0; 24 passed |
| `pnpm test --` administration-surfaces, save-to-quiz, chat-app | 0; 29 passed |
| `pnpm typecheck` | 0 |
| `pnpm lint` | 0 |
| `pnpm build` | 0 |
| `uv run python scripts/check_frontend_action_inventory.py` | 0 |
| `uv run python -m pytest tests/contract/test_pdf_eval_api.py` | 0; 15 passed |

PATCH/PUT/approve/delete bodies use `expected_row_version`. Passages require
`document_id`. Compare citations remains labelled **not Recall@10**.

## Proven

- Status 403 still gates the workspace before private fields.
- First page requests `limit=20`. Load more uses the keyset cursor.
- Review filter posts `review_status=approved`. Holdout is not a split option.
- Gold picker can select a non-citation chunk and PUT 0–3 IDs.
- Stale gold disables Approve and shows remap copy. Aggregate stale banner
  uses `stale_gold_count`.
- 409 `stale_row_version` reloads the case. Delete Cancel returns focus.
- Regenerate pending, inserted unapproved drafts, 409 `capacity_exceeded`,
  and generic error are distinct.
- Hostile query-class strings remain text. RTL passage preview uses
  `dir="auto"`. AI-test Reveal stays disabled until a completed run.

## Unverified

- Live regenerate and gold PUT against hosted quiz RPCs (UI tests use fakes).
- Recall@10 scoreboard (P06-35).
- Managed region/DPA/backup matrix rows. Residual-risk exception from P06-27
  still applies.

## Handoff

Next packet is
[P06-35](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/35-admin-exam-board.md)
(Admin Recall@10 scoreboard, exam progress, qualification confirmation).
Do not start P06-11 until P06-36 closes.
