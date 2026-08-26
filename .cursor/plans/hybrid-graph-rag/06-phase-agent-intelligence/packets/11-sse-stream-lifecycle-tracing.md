---
phase: 6
packet: 11
status: pending
title: "Drain successful LangGraph streams and classify expected cancellation without hiding real trace errors."
requirement_ids: [P06-11]
---

# Packet 11 — Drain successful LangGraph streams and classify expected cancellation without hiding real trace errors.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md)
and
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

## Preconditions

- Packet 10 routing contracts exist or are explicitly out of this packet's
  edit set. This packet does not change knowledge-scope classification.
- Production call site
  [`apps/backend/src/smart_rag_api/services/sse_stream.py`](../../../../../apps/backend/src/smart_rag_api/services/sse_stream.py)
  `LangGraphQueryRunExecutor.execute()` is inspectable.
- Current successful flow yields a terminal event and returns from inside
  `async for raw_chunk in compiled.astream(...)`, then unconditionally calls
  `aclose()`, which injects `GeneratorExit` into LangGraph's unfinished async
  generator.

## Allowed outputs

- Executor lifecycle refactor in `sse_stream.py` without changing the public
  `QueryRunExecutor` protocol.
- Parent-trace helper updates in
  [`packages/core/src/smart_rag_core/observability/query_run_trace.py`](../../../../../packages/core/src/smart_rag_core/observability/query_run_trace.py).
- Tests in `tests/unit/test_query_sse_executor.py` and
  `tests/unit/test_query_run_sse_trace.py`, plus existing SSE mapping/resume/
  heartbeat regressions.

## Forbidden outputs

- Knowledge-scope routing, general-chat generation, Studio live, or frontend
  changes.
- Global `GeneratorExit` suppression or blanket
  `exceptions_to_handle=(GeneratorExit,)`.
- Exporting query text, messages, source text, JWT, citations, or secrets.
- A second SSE terminal or a second settlement.

## Ordered actions

1. Write failing tests first. In
   `tests/unit/test_query_sse_executor.py`, add a typed
   `_RecordingAsyncStream` with ordered chunks, `consumed` count,
   `aclose_count`, `__aiter__`, `__anext__`, and `aclose`.
   Required failing cases:
   - terminal verify chunk followed by one harmless trailing chunk: all
     chunks consumed, one `completed`, `aclose_count == 0`, successful
     terminal committed once;
   - mid-stream cancel: `aclose_count == 1`, `stream_exhausted is False`,
     termination reason `cancelled`;
   - natural graph error: exactly one error terminal, no successful
     settlement;
   - consumer disconnect without explicit cancel: HTTP consumer may stop,
     background executor remains resumable.
2. Refactor `LangGraphQueryRunExecutor.execute()` with:

   ```python
   stream_iter: AsyncIterator[object] | None = None
   stream_exhausted = False
   stream_aclose_called = False
   terminal_yielded = False
   terminal_event_type: str | None = None
   termination_reason = "unknown"
   successful_terminal_committed = False
   ```

   Rules:
   1. For pre-stream deadline, yield existing deadline/partial events, record
      reason `deadline`, and return before opening `astream`.
   2. During `async for raw_chunk in stream_iter`: if cancel event is set,
      set reason `cancelled` and `break`; map/yield drafts exactly as today;
      on first terminal, record type/reason; commit successful terminal once
      for `completed`/`partial`; do not return after terminal; continue
      draining `astream` to `StopAsyncIteration`.
   3. Set `stream_exhausted=True` only after natural async-loop exhaustion.
   4. Keep `QuerySseMapper` terminal suppression; trailing graph updates must
      emit no second SSE terminal.
   5. In `finally`, close the DB connection exactly once.
   6. Call `stream_iter.aclose()` only when the stream exists, did not
      naturally exhaust, and was not already closed.
   7. Await `aclose()` through a task and `asyncio.shield`. If the outer task
      is cancelled, await the close task to completion and then re-raise.
      Re-raise `GeneratorExit`; do not silently convert it to success.
   8. Store a sanitized termination summary on the concrete executor with
      `termination_reason`, `terminal_event_type`, and `stream_exhausted`.
3. In `SseStreamService._run_executor()`: remove the outer `break` on
   `live.cancel_event.is_set()`; append yielded events and let the executor
   perform cleanup; preserve exactly-one-terminal fallback behavior.
4. For explicit cancel: persist `cancelled` immediately; set `cancel_event`;
   allow `0.25` seconds cooperative cleanup; hard-cancel the executor task
   only if still running after that grace period; cancel heartbeat
   immediately; add tests for the grace timeout and no lingering task.
5. Remove the dead `query_run_trace_metadata(...)` build-and-delete path.
   Add parent span name `query.run.sse`, redactors that export only
   correlation IDs, hashed user ID, route, model/prompt versions, terminal
   type, termination reason, and exhausted bool, and an async traced invoker
   patterned after existing ingestion/eval helpers. Apply the existing
   governance gate before trace export. Open the parent trace in
   `_run_executor` around complete consumption of the executor.
6. Add `tests/unit/test_query_run_sse_trace.py` for completed, cancelled,
   real-error, redaction, and tracing-disabled cases.

## Acceptance checks

- Completed/partial streams exhaust naturally and do not call `aclose`.
- Successful LangSmith traces no longer show `GeneratorExit` as the intended
  completed-run behavior. Live LangSmith inspection may remain unverified
  until P06-15 if credentials are unavailable; unit/contract proof is
  required here.
- Cancelled streams close once and are tagged cancelled.
- Genuine errors remain errors.
- Exactly one terminal event and one settlement remain invariant.

```powershell
uv run pytest tests/unit/test_query_sse_executor.py tests/unit/test_query_sse_mapping.py tests/unit/test_sse_protocol.py tests/contract/test_sse_resume.py tests/contract/test_sse_heartbeat.py tests/unit/test_query_run_sse_trace.py -q
uv run ruff check apps/backend/src/smart_rag_api/services/sse_stream.py packages/core/src/smart_rag_core/observability/query_run_trace.py tests/unit/test_query_sse_executor.py tests/unit/test_query_run_sse_trace.py
uv run pyright apps/backend/src/smart_rag_api/services/sse_stream.py packages/core/src/smart_rag_core/observability/query_run_trace.py tests/unit/test_query_sse_executor.py tests/unit/test_query_run_sse_trace.py
```

## Negative tests

- Returning from inside `astream` after the first terminal, calling `aclose`
  on a naturally exhausted stream, converting `GeneratorExit` into success,
  emitting a second terminal, settling a cancelled/error run as completed, or
  exporting query/source/JWT canaries fails the packet.

## Stop routes

- Stop if the pinned LangGraph/LangSmith tracing API cannot open a parent
  span without a global `GeneratorExit` filter.
- Stop if an authorization, idempotency, cancellation, or exactly-one-
  terminal test cannot exercise the real boundary.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):
  stream-lifecycle fixtures, `aclose` counts, termination summaries, redaction
  proof, exact commands/exit codes, unverified live LangSmith inspection,
  rollback, and P06-12 handoff.
