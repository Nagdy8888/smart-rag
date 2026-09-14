---
phase: 6
packet: 35
status: complete
title: "Implement the Admin Recall@10 scoreboard, exam progress, and qualification confirmation."
requirement_ids: [P06-35]
---

# Packet 35 — Implement the Admin Recall@10 scoreboard, exam progress, and qualification confirmation.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

## Preconditions

- P06-32 exam APIs and P06-34 curation UI exist.

## Allowed outputs

- Report query and scoreboard.
- Development/qualification start controls, polling, progress, cancel,
  terminal, and missed-case drill-down UI.
- Owner E2E fixtures and tests/docs/action inventory.

## Forbidden outputs

- Hover-only explanatory text.
- Calling citation overlap Recall@10.
- Freeze or holdout controls.
- Question/answer/excerpt/raw ID lists in the scoreboard payload or DOM
  before authorized case-detail navigation.
- Replacing a prior official report on partial/failed/cancelled.

## Ordered actions

1. Replace CLI-only copy with: **All required gold chunks in the production
   Hybrid top 10: X of Y (Z%)**.
2. Show numerator, denominator, percentage, split, completed time,
   candidate/dataset short hashes, gate status/reason, degradation, and
   sample sufficiency.
3. Use an accessible disclosure for the metric definition.
4. Start development with an idempotency key and current dataset hash.
5. Before qualification, confirm this dataset/candidate has one attempt.
   Server remains authoritative.
6. Poll by exam ID with bounded interval/backoff until terminal. Resume an
   active run after page refresh.
7. Announce progress in a polite live region and provide Cancel.
8. On success, invalidate latest report and case-result queries.
9. On partial/failed/cancelled, retain prior official report and show safe
   diagnostic counts.
10. Add paginated hit/miss/failure case-ID drill-down linked to the case
    editor.

## Acceptance checks

- `present=false`, insufficient dataset, pass, fail, degradation, and
  latest-report states.
- queued → running → succeeded polling. Refresh reconnects.
- One-active conflict links the existing exam.
- Qualification confirmation and consumed 409.
- Members have no tab; direct API remains 403.
- Owner E2E covers visible tab, development start, persisted progress, and
  completed report using safe stubs or an explicitly provisioned live
  fixture.

## Negative tests

- Insufficient dataset never labels `gates_pass`.
- Metric copy names all required gold chunks and the full production corpus.
- No private case text in the report table.

## Stop routes

- Stop rather than run holdout to populate a scoreboard.
- Do not invent a freeze button.

## Required evidence

- Append frontend gates, Playwright owner/member results or blockers, and
  P06-36 handoff.
