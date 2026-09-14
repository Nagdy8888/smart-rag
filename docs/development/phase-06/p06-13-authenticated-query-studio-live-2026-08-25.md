# P06-13 — Authenticated `query_studio_live` (2026-08-25)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: add a separate Agent Server factory that admits a paid live
Studio run after JWKS, profile, revocation, rate, and Composite/Auto
budget checks. Unbound `query_studio` stays synthetic.

Factory signature source: pinned `langgraph==1.2.11` /
`langgraph-cli[inmem]==0.4.31` `langgraph_api._factory_utils` accepts
`make_graph(runtime: ServerRuntime)` (0/1/2-arg variants). Installed
`langgraph_sdk.runtime.ServerRuntime` documents
`execution_runtime is None` for introspection. Implemented:

```python
@asynccontextmanager
async def make_graph(runtime: ServerRuntime[None]) -> AsyncGenerator[StudioCompiledGraph, None]:
```

`langgraph.json` now registers `query_studio_live` at
`./src/smart_rag_agents/query/studio_live.py:make_graph`. The
`query_studio` entry is unchanged.

Import boundaries: `studio_live.py` / `live_runtime.py` /
`profile_snapshot.py` do not import `smart_rag_api` or FastAPI. Backend
`query_graph_runtime.py` and `profile_loader.py` re-export the moved
helpers. `AgentSettings` does not inherit `BackendSettings` and declares
no service-role field.

Admission/idempotency/redaction: same human message id reuses
`uuid5(STUDIO_LIVE_NAMESPACE, thread:turn:hash)`; a new turn id gets a
new key; role/version reload each seed; canary token is absent from
state JSON, settings repr, and graph schemas. Disabled/missing/invalid/
revoked tokens reject without `studio_local`. Introspection opens zero
sockets. The per-run connection closes on success, error, and cancel.

Verification:

| Command | Exit |
| --- | --- |
| `uv run pytest tests/contract/test_langgraph_config.py tests/contract/test_import_boundaries.py tests/unit/test_query_studio.py tests/unit/test_query_studio_live.py tests/unit/test_query_graph_runtime.py -q` | 0 (52 passed) |
| `uv run ruff check` on `studio_live.py`, `live_runtime.py`, `graph.py`, `profile_snapshot.py` | 0 |
| `uv run pyright` on the same four files | 0 |

Unverified: live JWT + hosted Supabase + budget + OpenAI + retrieval
success. Marked **blocked** until those credentials and services are
available. Do not treat mocked admit as live proof.

Rollback: remove the `query_studio_live` graph entry; leave
`query_studio` unbound. FastAPI SSE wiring is unchanged.

Handoff to P06-14: add answer-origin, clarification, and citation-safe
behavior to the main chat UI. `KNOWN_SSE_EVENT_TYPES` must include
`answer_origin`.

## 2026-09-13 close-out (resume after P06-36)

Wrapper Packet 13 stayed unchecked while hosted eval packets ran. Studio
live tests were split into `test_query_studio_admission.py`,
`test_query_studio_auth.py`, `test_query_studio_execution.py`, and
`test_query_studio_introspection.py`. Unbound `query_studio` is unchanged.
Live JWT success remains **blocked**.

2026-09-13 commands (`APP_ENV=test`, `ALLOW_TEST_IDENTITY=true`,
`MOCK_MODEL_MODE=true`):

| Command | Exit |
| --- | --- |
| `uv run pytest tests/contract/test_langgraph_config.py tests/contract/test_import_boundaries.py tests/unit/test_query_studio.py tests/unit/test_query_studio_admission.py tests/unit/test_query_studio_auth.py tests/unit/test_query_studio_execution.py tests/unit/test_query_studio_introspection.py tests/unit/test_query_graph_runtime.py -q` | 0 |
| `uv run ruff check` on `studio_live.py`, `live_runtime.py`, `graph.py`, `profile_snapshot.py` | 0 |
| `uv run pyright` on the same four files | 0 |
