---
title: P06-35 Admin Recall@10 scoreboard, exam progress, qualification
owner: engineering-lead
status: draft
last-reviewed: 2026-09-13
audience: engineering, reviewers, frontend, security
---

# P06-35 — Implement the Admin Recall@10 scoreboard, exam progress, and qualification confirmation (2026-09-13)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: implement the Admin Recall@10 scoreboard, exam progress, and
qualification confirmation.

User directed continuous execution through P06-36.

## Plan requirement

Quote: implement the Admin Recall@10 scoreboard, exam progress, and
qualification confirmation.

Positive checks: `present=false`, insufficient dataset, pass, fail,
degradation, latest-report; queued → running → succeeded polling; refresh
reconnects; one-active conflict links the stored exam; qualification
confirmation and consumed 409; members have no tab; owner E2E with
safe stubs or a provisioned live fixture.

Negative checks: insufficient dataset never labels `gates_pass`; metric
copy names all required gold chunks and the full production corpus; no
private case text in the report table.

## Files

- [evaluation-exam-board.tsx](../../../apps/frontend/src/components/evaluation/evaluation-exam-board.tsx)
- [use-eval-exam.ts](../../../apps/frontend/src/components/evaluation/hooks/use-eval-exam.ts)
- [eval-exam-pointer.ts](../../../apps/frontend/src/lib/eval-exam-pointer.ts)
- [eval-workspace.ts](../../../apps/frontend/src/lib/eval-workspace.ts)
- [pdf-eval.ts](../../../apps/frontend/src/lib/api/pdf-eval.ts)
- [action-inventory.json](../../frontend/action-inventory.json)
- [PDF_EVAL_WORKSPACE.md](../../evaluation/PDF_EVAL_WORKSPACE.md)
- [ADMINISTRATION.md](../../frontend/ADMINISTRATION.md)
- [API_UI_MAPPING.md](../../frontend/API_UI_MAPPING.md)

Headline copy is **All required gold chunks in the production Hybrid top
10: X of Y (Z%)**. Citation overlap stays **not Recall@10**. No freeze
or holdout control. Resume uses a sessionStorage pointer because
`already_running` does not return the other exam id.

## Verification

| Command | Exit |
| --- | --- |
| `pnpm test --` evaluation, pdf-eval, eval-workspace | 0; 40 passed |
| `pnpm test --` evaluation-exam-board, eval-exam-pointer, pdf-eval API | 0; included in 42 across those files plus panel |
| `pnpm test --` administration-surfaces, save-to-quiz, chat-app | 0; 58 passed |
| `pnpm typecheck` | 0 |
| `pnpm lint` | 0 |
| `pnpm build` | 0 |
| `uv run python scripts/check_frontend_action_inventory.py` | 0 |
| `uv run python -m pytest tests/contract/test_pdf_eval_api.py tests/contract/test_pdf_eval_exam_api.py` | 0; 22 passed |
| `pnpm exec playwright test tests/e2e/administration-surfaces.spec.ts` | 0; 1 passed, live specs skipped |

Playwright live owner/member journeys skip when `E2E_LIVE_EMAIL` /
`E2E_LIVE_PASSWORD` are unset (or local FastAPI is down). The unauthenticated
redirect passed. Vitest covers present=false, empty_dataset, pass/fail,
polling, pointer resume, qualification confirm/consumed, and count-only
rows. Members still have no Evaluation tab in the member chrome spec.

## Proven

- Official headline names all required gold chunks and the production Hybrid top 10.
- `present=false` does not show `gates_pass`. Empty dataset shows counts only.
- `gates_pass=false` shows degraded retrieve-gate copy. Partial/failed exams keep the prior official report.
- queued → running → succeeded polling invalidates the latest report. Refresh reconnects from sessionStorage.
- Qualification confirms before POST. `qualification_consumed` 409 is server-authoritative.
- Report rows are ordinal / hit / gold_count only. Compare citations remains **not Recall@10**.

## Unverified

- Live owner Playwright against a provisioned FastAPI session (credentials unset in this run).
- Live hosted exam scoring (HTTP 202 plus supervisor). Do not treat mocks as live proof.
- Managed region/DPA/backup matrix rows. Residual-risk exception from P06-27 still applies.

## Handoff

Next packet is
[P06-36](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/36-hosted-eval-verification.md)
(integrated verification, docs close). Do not start P06-11 until P06-36
closes.
