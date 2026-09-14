---
phase: 6
packet: 34
status: complete
title: "Implement Admin case review, gold picker, stale repair, and draft regeneration."
requirement_ids: [P06-34]
---

# Packet 34 — Implement Admin case review, gold picker, stale repair, and draft regeneration.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md),
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

Do not add exam scoreboard/progress UI here.

## Preconditions

- P06-29 case APIs exist. Inspect `evaluation-panel.tsx` and evaluation tests.

## Allowed outputs

- Paginated/filterable case list, full editor, independent current-passage
  gold picker, stale repair, regenerate, reject/delete.
- Frontend API clients/types/query keys/tests/docs.

## Forbidden outputs

- Exam start/scoreboard UI.
- Holdout cases. Freeze controls.
- Requiring users to interpret UUIDs alone.
- Self-approving generated drafts.

## Ordered actions

1. Preserve the real server authorization gate before private content.
2. Add split/review/gold-state filters and Load more pagination (20, max 60).
3. Make expected answer, atomic facts, query class, and required terms
   editable.
4. Implement a labeled 0–3 gold picker using authorized current passages.
   Show document title, page label/number, heading, and bounded escaped
   preview.
5. Show per-case gold state and an aggregate stale banner. Stale gold blocks
   approval/exam.
6. On version replacement, guide remap and require reapproval.
7. Add approve, reject, delete confirmation, and next-case behavior with
   row-version conflict reload.
8. Add document-scoped Regenerate drafts; generated rows remain unapproved.
9. Keep manual AI test and Compare citations labelled not Recall@10.
10. Expected answer stays collapsed until a completed manual AI run where
    that control applies.

## Acceptance checks

- First 20 plus pagination to 60. Filters and empty/loading/error/403.
- Gold 0–3 selection including chunks that were not citations.
- Edit/gold change clears approval. Stale version blocks approve.
- Hostile strings and RTL text render safely. Keyboard-only picker.

## Negative tests

- Members have no tab; direct API remains 403.
- Stale row reload on 409.
- Delete confirmation returns focus.
- Regenerate pending/success/409/error.

## Stop routes

- Stop rather than add Run exam to this packet.
- Do not auto-import `.private-eval/`.

## Required evidence

- Append evaluation-panel tests, frontend gates, and P06-35 handoff.
