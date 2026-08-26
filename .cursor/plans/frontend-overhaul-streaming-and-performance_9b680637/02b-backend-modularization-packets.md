# Candidate Backend Streaming Modularization Packets

Status: **candidate, non-canonical**

These move-only packets prevent streaming work from expanding backend god
files. Run one ID per model run and keep all existing imports working through
temporary compatibility facades.

## Current and exit physical-line budgets

```text
apps/agents/src/smart_rag_agents/query/graph.py
  476 -> <=300, topology/edges/compile only

apps/backend/src/smart_rag_api/services/sse/executors.py
  527 -> <=100, compatibility exports only

apps/backend/src/smart_rag_api/services/sse/executor_support.py
  321 -> <=100, retained compatibility exports

apps/backend/src/smart_rag_api/services/query_sse_mapping.py
  363 -> <=100, compatibility exports only

apps/backend/src/smart_rag_api/services/sse/service.py
  492 -> <=300, public attach/orchestration only

apps/backend/src/smart_rag_api/services/sse/service_persist.py
  358 -> <=100, compatibility exports/mixin only
```

No BEP packet may begin until its named BMOD prerequisite passes.
All values are physical lines counted with
`len(Path.read_text(encoding="utf-8").splitlines())`.

## BMOD-01 — Extract bound graph-node construction

**Objective:** make `graph.py` a topology module before adding progress wrappers.

**Add**

- `apps/agents/src/smart_rag_agents/query/runtime/bound_nodes.py`;
- `tests/unit/test_query_node_bindings.py`.

Move the nested production node callables from `build_query_graph` into a typed
`BoundQueryNodes` owner. Preserve each callable's
`(state, Runtime[QueryGraphContext]) -> QueryGraphState` contract and existing
`deps_from_runtime` behavior.

`graph.py` keeps:

- route functions;
- exact `builder.add_node` stage names;
- edges/conditional edges;
- studio-only node selection;
- compile/checkpointer entry point.

The new owner contains no LangGraph topology edges and emits no progress yet.

**Acceptance**

- registered node names and route paths are byte-for-byte equivalent;
- studio local/live still compile;
- `graph.py` ≤300 physical lines;
- new module ≤300;
- import-boundary and graph-route tests pass.

```powershell
uv run pytest tests/unit/test_query_node_bindings.py tests/unit/test_scope_graph_routes.py tests/contract/test_langgraph_config.py -q
uv run ruff check apps/agents/src/smart_rag_agents/query/graph.py apps/agents/src/smart_rag_agents/query/runtime/bound_nodes.py
```

## BMOD-02 — Extract executor protocol and fixture

**Objective:** move non-production executor contracts without behavior changes.

**Add**

- `apps/backend/src/smart_rag_api/services/sse/executor_protocol.py`;
- `apps/backend/src/smart_rag_api/services/sse/fixture_executor.py`.

Move `QueryRunExecutor` and `FixtureQueryRunExecutor` verbatim. Keep re-exports
from `executors.py` so current imports/tests do not change in this packet.

Test fixture start count, hold/cancel, extra event order, and optional terminal.

## BMOD-03 — Extract LangGraph runtime/checkpointer setup

**Objective:** move process binding and checkpointer construction from the
production executor class into a focused owner while preserving behavior.

**Add**

- `apps/backend/src/smart_rag_api/services/sse/langgraph_runtime.py`;
- focused runtime factory tests.

Move the current `_process_bindings`, `_bind_memory_store`,
`_ensure_async_checkpointer`, and `_compiled_query_graph` responsibilities into
one typed factory/service. Preserve lazy initialization, lock ownership,
Postgres setup prohibitions, process reuse, and fail-closed errors.

No stream mode or SSE behavior changes in this packet. New module ≤280 lines.

## BMOD-04 — Split executor lifecycle support

**Objective:** split `executor_support.py` by persistence/lifecycle concern.

**Add**

- `apps/backend/src/smart_rag_api/services/sse/stream_lifecycle.py`: close,
  termination, and token/usage accounting helpers;
- `apps/backend/src/smart_rag_api/services/sse/answer_persistence.py`: terminal
  commit, optional summary, and assistant-message persistence;
- focused tests beside existing lifecycle/settlement tests.

Keep database commit order, caller/RLS context, cancellation, first-terminal,
summary budget, and assistant-message idempotency unchanged. Do not swallow
persistence errors.

Leave `executor_support.py` as a ≤100-line compatibility mixin/export only if
needed during migration.

## BMOD-05 — Isolate the production executor

**Objective:** complete the executor strangler before BEP-06 changes streaming.

**Add**

- `apps/backend/src/smart_rag_api/services/sse/langgraph_executor.py`.

Move `LangGraphQueryRunExecutor` into this owner. It composes the runtime
factory and lifecycle/persistence helpers. Keep its existing
`stream_mode="updates"` behavior during this move-only packet.

Make `executors.py` a ≤100-line explicit compatibility barrel exporting:

- `QueryRunExecutor`;
- `FixtureQueryRunExecutor`;
- `LangGraphQueryRunExecutor`.

Every production module must be ≤300 physical lines. Run lifecycle,
verified-final, settlement, event-store, and resume tests before BEP-06.

```powershell
uv run pytest tests/unit/test_query_sse_lifecycle.py tests/unit/test_query_sse_verified_final.py tests/unit/test_query_sse_settlement.py tests/unit/test_query_sse_event_store.py tests/contract/test_sse_resume.py -q
```

## BMOD-06 — Decompose the current SSE mapper

**Objective:** create mapping owners before adding node/tool events.

**Add under
`apps/backend/src/smart_rag_api/services/sse/mapping/`**

- `status.py`: existing status outcome mapping;
- `citations.py`: citation preview mapping;
- `usage.py`: usage payload mapping;
- `limitations.py`: limitation mapping;
- `contracts.py`: mapper payload allow-fields and `assert_catalog_event`;
- `verified.py`: answer payload extraction, verified hold/release, chunking;
- `mapper.py`: current `QuerySseMapper` orchestration;
- `__init__.py`: explicit public exports.

Move behavior verbatim. Keep
`apps/backend/src/smart_rag_api/services/query_sse_mapping.py` as a ≤100-line
compatibility facade exporting all currently imported names.

**Acceptance**

- no draft answer text is released;
- current event order/payloads are identical;
- mapper, verified-final, lifecycle, and protocol tests pass;
- every new mapping module ≤250 physical lines;
- no progress/diagnostic event is added until BEP-05.

```powershell
uv run pytest tests/unit/test_query_sse_mapping.py tests/unit/test_query_sse_verified_final.py tests/unit/test_query_sse_lifecycle.py tests/unit/test_sse_protocol.py -q
```

## BMOD-07 — Split stream attach and run orchestration

**Objective:** reduce
`apps/backend/src/smart_rag_api/services/sse/service.py` from 492 physical
lines before progress traffic increases its responsibilities.

**Add**

- `apps/backend/src/smart_rag_api/services/sse/run_access.py`: admitted-run
  ownership/readability/cancel notification;
- `apps/backend/src/smart_rag_api/services/sse/run_orchestration.py`:
  start-once, executor task, and heartbeat task helpers;
- focused service lifecycle tests.

Keep `SseStreamService` public construction and `iter_frames` orchestration in
`service.py`. Extract behavior verbatim and inject store/registry/executor
dependencies explicitly; do not create module globals.

**Acceptance**

- `service.py` ≤300 physical lines;
- new modules ≤300 physical lines;
- persist-before-flush, one start, heartbeat, cancel, attach/replay, and
  settlement behavior are unchanged;
- no progress event is added in this move-only packet.

## BMOD-08 — Split persistence, append, replay, and cancel helpers

**Objective:** reduce `service_persist.py` from 358 physical lines.

**Add**

- `apps/backend/src/smart_rag_api/services/sse/event_append.py`: sync/async
  append, catalog validation, and append-failure logging;
- `apps/backend/src/smart_rag_api/services/sse/run_settlement.py`: schema,
  durable start, worker-unavailable, and reservation settlement;
- `apps/backend/src/smart_rag_api/services/sse/replay_cancel.py`: terminal
  lookup, replay, cooperative cancel, and task cleanup.

Keep `service_persist.py` as a ≤100-physical-line compatibility composition
surface only if callers still require it. Preserve sequence allocation,
first-terminal behavior, RLS/caller context, commit order, idempotent
settlement, and cancellation.

Run event-store, lifecycle, settlement, heartbeat, cancel, and resume tests.

## BMOD-09 — Enforce stream-path budgets

**Objective:** make the no-god-file exit machine-verifiable using the
repository's physical-line metric.

**Modify**

- `tests/contract/architecture_scanner.py`;
- `tests/contract/test_architecture_budgets.py`.

**Add:** `tests/contract/test_stream_architecture_budgets.py`.

Add exact stream-path targets for:

- `graph.py` and every new bound-node module;
- `executors.py`, `executor_support.py`, and their extracted owners;
- `service.py`, `service_persist.py`, and their extracted owners;
- `query_sse_mapping.py` and `services/sse/mapping/`.

Facades are ≤100 physical lines and runtime owners ≤300. Do not lower the
repository-wide hard cap in a way that fails unrelated phases; add focused
stream-path assertions. No exception entry is allowed for a file this packet is
supposed to shrink.

```powershell
uv run pytest tests/contract/test_architecture_budgets.py tests/contract/test_stream_architecture_budgets.py -q
```

## Dependency order

1. BMOD-01 before BEP-03.
2. BMOD-02 → BMOD-03 → BMOD-04 → BMOD-05 before BEP-06.
3. BMOD-06 before BEP-01 and BEP-05.
4. BMOD-07 → BMOD-08 before P08B settlement/terminal repairs and all BEP work.
5. BMOD-09 runs after BMOD-01 through BMOD-08 and before BEP-01.
6. All are characterization/move-only; a failed parity test stops progress work.
