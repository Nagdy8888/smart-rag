# Cleanup packet 5 — Runtime, Studio, and persistence (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: split `live_runtime.py` into adapters, process
bindings, and run-scoped factories; split Studio into input, local seed,
live auth/admission, and factory modules; move checkpointer/store under
query persistence; prove LangGraph 1.2.11 `context_schema` +
`invoke(..., context=)` compile reuse, or record the blocker.

Acceptance checks:

- one compiled graph plus two concurrent invocations with isolated deps;
- cancel one run without leaking into the other;
- module-level Studio graph stays unbound;
- `langgraph.json` entry points unchanged;
- FastAPI-only `query_graph_runtime.py` still owns `app.state`.

Proven:

- Pinned `langgraph==1.2.11` exposes `StateGraph(..., context_schema=)`
  and `Pregel.invoke/astream(..., context=)`. Invoke without context
  yields `runtime.context is None`; wrappers use
  `deps_from_runtime(runtime, fallback)`.
- `compile_query_graph()` compiles the static topology once. SSE
  `LangGraphQueryRunExecutor` caches that compile per checkpointer
  identity and injects `QueryGraphContext(deps=...)` on `astream`.
  Process caches must not close over a prior run's connection.
- Studio Agent Server still does not pass `context=`. Live Studio keeps
  per-execution compile with closed-over fallback deps. No identity-keyed
  or global current-run cache was added.
- Runtime: `runtime/bindings.py`, `runtime/adapters.py`,
  `runtime/deps_factory.py`, facade `live_runtime.py`.
- Studio: `studio/input.py`, `studio/local.py`, `studio/live_auth.py`,
  `studio/live_admission.py`, `studio/live_factory.py`,
  `studio/tracing.py`, plus `studio.py` / `studio_live.py` /
  `studio_tracing.py` facades.
- Persistence: `persistence/checkpointer.py`, `persistence/store.py`,
  plus `checkpointer.py` / `store.py` facades including
  `QUERY_CHECKPOINTER_POOL_MAX_SIZE`.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run ruff check apps/agents/src/smart_rag_agents/query apps/backend/src/smart_rag_api/services/sse_stream.py tests/unit/test_query_graph_compile_reuse.py` | 0 | clean |
| `uv run pytest tests/unit/test_package_imports.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_graph_compile_reuse.py -q` | 0 | passed |
| `uv run pytest tests/unit/test_query_studio.py tests/unit/test_query_studio_live.py tests/unit/test_query_profile_gateway.py tests/unit/test_scope_graph_routes.py -q` | 0 | passed |
| `uv run pytest tests/unit/test_postgres_dsn.py tests/unit/test_readiness.py tests/contract/test_langgraph_config.py tests/contract/test_checkpoint_postgres.py -q` | 0 | passed |

Unverified: live LangGraph Studio Agent Server injecting
`QueryGraphContext` (API does not pass `context=` today).

Deviations: context-loader and Studio introspection tests now patch
`runtime.adapters` / `runtime.deps_factory` because those modules own
`psycopg.connect`. `live_runtime.py` still re-exports `psycopg`.

Rollback: restore the `live_runtime.py` / Studio / checkpointer monoliths
and per-run `compile_query_graph(deps)` in SSE.

Handoff to cleanup packet 6: split `sse_stream.py` into chunk parsing,
executors, registry, service, and HTTP framing; keep one heartbeat
writer and the compile-once cache.
