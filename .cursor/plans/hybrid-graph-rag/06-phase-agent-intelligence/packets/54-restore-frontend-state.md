---
phase: 6
packet: 54
status: pending
title: "Restore per-turn citations and feedback after reload and add accessible conversation deletion confirmation."
requirement_ids: [P06-54]
---

# Packet 54 — Restore per-turn citations and feedback after reload and add accessible conversation deletion confirmation.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md).

Do not load Python migration skills.

## Preconditions

- P06-53 is recorded. Branch is `fix/rag-reliability-and-citations`.
- Transcript rows expose optional `run_id`, `citation_count`, and
  `source_kind`. Inspect chat hooks, answer surface, ChatApp line
  budget, and existing `ConfirmDialog` before editing.

## Allowed outputs

- `apps/frontend/src/lib/api.ts` and `apps/frontend/src/lib/api/`
  transcript/citation parsers
- `apps/frontend/src/components/chat/hooks/use-chat-queries.ts`
- `apps/frontend/src/components/chat/hooks/use-chat-scope.ts` only if
  required for viewing-run identity
- `apps/frontend/src/components/chat/answer-surface.tsx`
- `apps/frontend/src/components/chat/chat-app.tsx`
- `apps/frontend/src/components/chat/chat-stage.tsx`
- Conversation action hooks that already own delete
- Tests listed below, `CORE_RAG_SURFACES.md` / API mapping docs, and
  packet evidence

## Forbidden outputs

- Writing a completed historical run into the reconnect pointer.
- Unbounded citation-detail fetch per transcript row.
- A second global store, direct Supabase table query, or replacement
  dialog primitive.
- Weakening server-side immediate deletion.
- Exceeding ChatApp architecture budget (320 lines).
- Backend SQL in this packet.

## Ordered actions

1. Keep three identities: `activeRunId` (in-flight SSE),
   `viewingRunId` (selected historical turn), `latestSettledRunId`
   (newest transcript assistant with `run_id`).
2. Render `Sources (citation_count)` without fetching details.
   Selection fetches `GET /runs/{run_id}/citations` then one detail
   request. At most one list and one detail in flight per selection.
3. Live answers keep active-run citations. Suppress duplicate
   live/historical rendering with the existing settled-turn overlay.
4. Feedback targets `activeRunId` only while a live answer is
   terminal; otherwise `viewingRunId ?? latestSettledRunId`. Disable
   submit without a settled assistant row.
5. General answers with `citation_count=0` show no Sources control.
6. On conversation change, clear viewing/citation/feedback state.
7. Confirm deletion with existing `ConfirmDialog`. Title: `Delete
   conversation?`. Initial focus Cancel. Escape/Cancel send no
   request. Confirm sends exactly one DELETE and invalidates queries.

## Acceptance checks

- Historical run IDs do not alter active run pointers.
- Details fetch only on selection.
- Each historical assistant shows its own count and opens its own run.
- Hostile titles/excerpts remain text.
- Remount/reload restores Company and Web Sources.
- Switching conversations does not retain old citations.
- Historical feedback targets the correct run once.
- Delete dialog appears before DELETE; Cancel sends zero requests;
  Confirm sends one; focus returns.

## Negative tests

- Fetching citation detail for every transcript row fails.
- Binding feedback to a live reconnect pointer after reload fails.
- Confirm sending two DELETEs fails.

## Stop routes

- Stop if ChatApp would exceed its architecture budget after a
  required split.
- Stop if restore would require storing excerpts in browser storage.
- Do not start Packet 55 Postgres work.

## Required evidence

- Targeted Vitest, eslint, tsc, build, and Playwright core-rag
  surfaces.
- Commands:

  ```powershell
  pnpm --filter smart-rag-frontend exec vitest run src/components/chat/hooks/use-chat-queries.test.tsx src/components/chat/answer-surface.test.tsx src/components/chat-app.test.tsx src/components/chat/hooks/use-conversation-actions.test.tsx src/lib/api.test.ts
  pnpm --filter smart-rag-frontend exec eslint .
  pnpm --filter smart-rag-frontend exec tsc --noEmit
  pnpm --filter smart-rag-frontend build
  pnpm --filter smart-rag-frontend exec playwright test tests/e2e/core-rag-surfaces.spec.ts
  git diff --check
  ```

- Commit `fix(frontend): restore citations feedback and delete safety`.
