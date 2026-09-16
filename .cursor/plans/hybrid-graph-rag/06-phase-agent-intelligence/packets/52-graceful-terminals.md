---
phase: 6
packet: 52
status: complete
title: "Map insufficient evidence/refusal/deadline to one truthful partial outcome and unify visible/accessibility copy."
requirement_ids: [P06-52]
---

# Packet 52 — Map insufficient evidence/refusal/deadline to one truthful partial outcome and unify visible/accessibility copy.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md),
[`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md).

## Preconditions

- P06-51 is recorded. Branch is `fix/rag-reliability-and-citations`.
- Inspect SSE mapping modules, `failure-copy.ts`, progress timeline,
  and chat banners before editing.

## Allowed outputs

- `apps/backend/src/smart_rag_api/services/sse/mapping/status.py`
- `apps/backend/src/smart_rag_api/services/sse/mapping/verified.py`
- `apps/backend/src/smart_rag_api/services/sse/mapping/mapper.py`
- Related SSE mapping helpers already owned by those modules
- `apps/frontend/src/lib/failure-copy.ts`
- `apps/frontend/src/components/chat/run-progress-timeline.tsx`
- `apps/frontend/src/components/chat/chat-banners.tsx`
- Tests listed below, docs that already describe SSE terminals, and
  packet evidence

## Forbidden outputs

- Emitting both `partial` and `error` for one run.
- Using `empty_answer` for expected refusal/deadline/bound outcomes.
- Streaming internal exception text or source text.
- Changing additive OpenAPI event names incompatibly.
- SQL, prompt, or worker topology changes.
- Starting Packet 53 transcript SQL.

## Ordered actions

1. Separate expected outcomes (`insufficient_evidence`, `refused`,
   deadline/budget partial) from faults (`run_failed`, blank verified
   output).
2. Expected outcomes emit a limitation/partial sequence with exactly
   one terminal event, never `error`/`empty_answer`.
3. Keep `empty_answer` only when a supposedly releasable verified
   payload is blank.
4. Mapper must be idempotent when the verify update is seen twice.
5. Unify visible, progress, and screen-reader copy. “Something went
   wrong” is reserved for unknown/server faults.
6. Insufficient evidence explains that company sources could not
   support an answer and suggests narrowing the question.

## Acceptance checks

- Verified complete: token deltas then exactly one `completed`.
- Verified partial: tokens then optional limitation then exactly one
  `partial`.
- Insufficient evidence/refused: non-empty refusal token, limitation
  `insufficient_evidence`, exactly one `partial`, no `error`.
- Deadline before generation: `deadline` then non-empty partial token
  when available then exactly one `partial {reason:"deadline_exhausted"}`.
- Blank verified payload: exactly one `error {code:"empty_answer"}`.
- Unknown failure: exactly one sanitized `error`.
- Visible and assertive copy match and are not generic for expected
  refusals.

## Negative tests

- Mapping company refusal to HTTP/SSE `error` fails the packet.
- Two terminal events for one run fails the packet.
- Generic “Something went wrong” for insufficient evidence fails.

## Stop routes

- Stop if the persisted event store would allow two terminals.
- Stop if copy would disclose source text or exception detail.
- Do not start Packet 53 migrations.

## Required evidence

- SSE mapping tests, frontend copy tests, ruff, vitest.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_query_sse_mapping.py tests/unit/test_query_sse_verified_final.py tests/unit/test_query_sse_progress_ordering.py tests/contract/test_sse_resume.py -q
  pnpm --filter smart-rag-frontend exec vitest run src/lib/failure-copy.test.ts src/lib/chat-view.test.ts src/components/chat/run-progress-timeline.test.tsx src/components/chat/chat-banners.test.tsx
  git diff --check
  ```

- Commit `fix(stream): map insufficient evidence to graceful outcomes`.
