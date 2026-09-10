---
phase: 6
packet: 22
status: complete
title: "Add the Admin Evaluation workspace for review, approval, and AI comparison."
requirement_ids: [P06-22]
---

# Packet 22 — Add the Admin Evaluation workspace for review, approval, and AI comparison.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Also read [`../../08-phase-frontend-integration/00-shared-contracts.md`](../../08-phase-frontend-integration/00-shared-contracts.md)
and [`../../08-phase-frontend-integration/00-visual-contract.md`](../../08-phase-frontend-integration/00-visual-contract.md).

Named skills: [`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md).

## Preconditions

- Packet 21 API exists. Packet 8/Phase 8 admin and chat patterns are
  inspectable. Do not renumber P08-22/P08-23.

## Allowed outputs

- `apps/frontend/src/components/evaluation/` and `lib/api/pdf-eval.ts`
- Additive Admin tab, shell navigation, query keys, docs, Vitest, and
  Playwright coverage

## Forbidden outputs

- Client route/profile override.
- Sending expected answers to the model.
- Holdout run controls.
- `dangerouslySetInnerHTML`.
- Treating hidden nav as authorization.

## Ordered actions

1. Add an Evaluation Admin tab only when `/api/meta` reports the capability.
2. Gate private content on a real owner/admin evaluation GET.
3. Build case list, editor, source preview, approve/reject/next, and AI
   test panel reusing authenticated admission/SSE/citations.
4. Keep expected answers collapsed until after the run and Reveal.
5. Compare citation IDs to gold chunk IDs after terminal completion.
6. Label ranked-ID Recall as CLI-only. This panel is a manual AI test.
7. Use `UserText`, drawers/sheets, focus return, `dir="auto"`, and reduced
   motion.

## Acceptance checks

- Capability absent hides the tab. Member/viewer still 403 on API.
- Hostile strings render as text. Stale edit reloads. Holdout cannot run.
- Reconnect does not create a second paid reservation.

## Negative tests

- Expected answer absent from the AI request body.
- Citation comparison before terminal completion is forbidden.

## Stop routes

- Stop if chat admission/SSE cannot be reused without a new paid protocol.
- Do not invent a second query runtime.

## Required evidence

- Append frontend lint/type/test/build/Playwright results and Packet 23
  handoff.
