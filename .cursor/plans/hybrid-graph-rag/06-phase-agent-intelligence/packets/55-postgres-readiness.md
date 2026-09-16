---
phase: 6
packet: 55
status: complete
title: "Add bounded transient reconnect behavior, stale SSE connection retirement, and honest query-runtime readiness."
requirement_ids: [P06-55]
---

# Packet 55 — Add bounded transient reconnect behavior, stale SSE connection retirement, and honest query-runtime readiness.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md).

## Preconditions

- P06-54 is recorded. Branch is `fix/rag-reliability-and-citations`.
- Inspect `postgres_connect.py`, `sse/store.py`, and `readiness.py`
  before editing.

## Allowed outputs

- `packages/core/src/smart_rag_core/settings/postgres_connect.py`
- `packages/core/src/smart_rag_core/sse/store.py`
- `apps/backend/src/smart_rag_api/services/readiness.py`
- Readiness router/schema modules already owned by that contract
- Tests listed below
- `docs/architecture/05-database-connections.md`
- `docs/development/CONFIGURATION.md`
- Readiness docs and packet evidence

## Forbidden outputs

- Retrying authentication, authorization, SQL, migration, or integrity
  failures.
- Logging DSNs or exception text that can include host/user values.
- Infinite background retry or hard-coded DNS resolvers.
- Auto-replaying append/terminal writes after an ambiguous failure.
- Changing Docker/Desktop host DNS to simulate failure.
- Worker/Compose topology (Packet 56).

## Ordered actions

1. Keep `prepare_threshold=None`. Add keyword-only `max_attempts=2`,
   `retry_budget_seconds=1.0`, injectable monotonic clock, and
   injectable sleep.
2. Retry only SQLSTATE class `08` or wrapped socket/DNS/connect
   transport failures with no SQLSTATE. One delay of at most 100 ms
   that never exceeds remaining deadline/budget.
3. Structured logs may contain only operation name, attempt number,
   and a fixed reason code.
4. `PostgresRunEventStore` reuses a connection for less than 60
   seconds idle. At or beyond 60 seconds, close/discard before the
   next yield. On any operation error, rollback best-effort,
   close/discard, and re-raise.
5. Read-only `list_after` may retry once only when failure occurred
   before any row was returned and no write occurred. Append/terminal
   settlement never auto-replays.
6. Track query-runtime warmup in app state. `query_ready` requires
   required dependencies AND `query_runtime_warmed` AND
   `run_event_store_ready`. `/health/live` stays process liveness.
   Public readiness content stays sanitized.

## Acceptance checks

- Active reuse within 60 seconds.
- 61-second idle replacement.
- Stale connection discarded; no ambiguous write replay.
- Transient fail-then-success uses two attempts; permanent auth
  failure uses one.
- Warmup failure and event-store failure clear `query_ready`;
  recovery restores it; no secrets appear.
- Forced read-side disconnect receives SSE rather than HTTP 500.

## Negative tests

- Retrying `InvalidPassword` fails the packet.
- Replaying a terminal append after transport failure fails.
- Putting exception text on `/health/ready` fails.

## Stop routes

- Stop if honest readiness would require changing the public live
  contract without an additive schema.
- Stop if reconnect would need unbounded retries.
- Do not start Packet 56 Compose/worker edits.

## Required evidence

- Unit and resume contract tests, ruff, pyright, docs.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_postgres_dsn.py tests/unit/test_query_sse_event_store.py tests/unit/test_readiness.py tests/contract/test_sse_resume.py -q
  uv run ruff check packages/core/src/smart_rag_core/settings/postgres_connect.py packages/core/src/smart_rag_core/sse/store.py apps/backend/src/smart_rag_api/services/readiness.py tests/unit/test_postgres_dsn.py tests/unit/test_query_sse_event_store.py tests/unit/test_readiness.py
  uv run pyright packages/core/src/smart_rag_core/settings/postgres_connect.py packages/core/src/smart_rag_core/sse/store.py apps/backend/src/smart_rag_api/services/readiness.py
  git diff --check
  ```

- Commit `fix(db): recover stale connections and tighten readiness`.
