---
phase: 6
packet: 14
status: pending
title: "Add answer-origin, clarification, and citation-safe behavior to the main chat UI."
requirement_ids: [P06-14]
---

# Packet 14 — Add answer-origin, clarification, and citation-safe behavior to the main chat UI.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

This is a Phase 6/Phase 8 co-owned additive UI amendment. Also read:

- [`../../08-phase-frontend-integration/00-shared-contracts.md`](../../08-phase-frontend-integration/00-shared-contracts.md)
- [`../../08-phase-frontend-integration/00-visual-contract.md`](../../08-phase-frontend-integration/00-visual-contract.md)
- [`../../shared/frontend/stitch-nextjs-contract.md`](../../shared/frontend/stitch-nextjs-contract.md)

Named skill:
[`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md).

Do not uncheck historical completed Phase 8 packets or renumber P08-22/P08-23.

## Preconditions

- Packet 12 emits additive `answer_origin` SSE events. Do not infer origin
  from route family.
- Existing Ask chat types, reducer, `AnswerSurface`, `Badge`, `StatusPill`,
  and `LimitationCallout` are inspectable.

## Allowed outputs

- Additive frontend types/reducer/helpers and Ask-surface rendering for
  origin, clarification, and citation visibility.
- Focused frontend unit/component tests and Phase 6 plus Phase 8 evidence
  notes.
- Existing chat CSS only as needed.

## Forbidden outputs

- New primitive components that duplicate `Badge` or `StatusPill`.
- Auth, reconnect, cancellation, idempotency, verified-final token holding,
  or source-drawer authorization changes.
- Inferring origin from `Hybrid`/`Combined`/`NoRetrieval` route pills.
- Showing citations for general/user-text/deterministic/ambiguous origins.

## Ordered actions

1. Add `ANSWER_ORIGINS` / `AnswerOrigin` in
   [`apps/frontend/src/lib/types.ts`](../../../../../apps/frontend/src/lib/types.ts).
   Add `"answer_origin"` to known additive events. Store
   `answerOrigin: AnswerOrigin | null` and `clarificationRequired: boolean`.
   Unknown origin values are tolerated and never crash the stream reducer.
2. Add [`apps/frontend/src/lib/answer-origin.ts`](../../../../../apps/frontend/src/lib/answer-origin.ts)
   with `answerOriginLabel`, `answerOriginTone`, and `shouldShowCitations`.
   Labels: `general_knowledge` → “General knowledge”; `company_documents` →
   “Company documents”; `user_supplied_text` → “Your text”; `deterministic`
   → “Assistant”; `ambiguous` → “Needs clarification”.
3. `AnswerSurface` receives `answerOrigin` and effective route. Render both
   in the answer header. Show citations only for `company_documents`. If
   origin is general/user-text/deterministic/ambiguous, hide stray citations
   defensively and record a client diagnostic. If origin is `null` from an
   older compatible server, preserve current citation behavior. For
   `ambiguous`, show existing `LimitationCallout` with: “This question mixes
   general knowledge and company documents. Ask one general question or one
   document question so the answer source stays clear.”
4. Update the empty state from “Ask your company knowledge” to: “Ask a
   general question, or ask about your company documents for a cited
   answer.”
5. Add/update `chat-view.test.ts`, `chat-app.test.tsx`, and
   `answer-surface.test.tsx` if present, otherwise add focused cases to the
   existing component test.

## Acceptance checks

- Each origin label renders.
- General/user-text/deterministic have no citations.
- Company origin shows citations.
- Null origin preserves old citation rendering.
- Ambiguous origin shows clarification and no citation chips.
- Route pill remains separate from origin.
- Unknown origin is tolerated.
- XSS strings in origin payload are never rendered as HTML.
- Keyboard/live-region behavior remains unchanged.

```powershell
pnpm --filter smart-rag-frontend test
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend typecheck
pnpm --filter smart-rag-frontend build
```

Run the focused Playwright Ask journey if the packet’s prerequisites are
available.

## Negative tests

- Inferring origin from route family, rendering unknown origin as a crash,
  showing citation chips on a general/ambiguous answer, or inserting origin
  payload as HTML fails the packet.

## Stop routes

- Stop if the inspected chat reducer cannot store an additive event without
  changing reconnect/idempotency/verified-final contracts.
- Do not invent a new SSE major version or a new primitive.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and
  [`phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
  origin/citation fixtures, exact frontend commands/exit codes, Playwright
  status or explicit skip reason, rollback, and P06-15 handoff.
