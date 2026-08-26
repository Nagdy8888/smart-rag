# Cleanup packet 6 — Backend SSE split (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: split `sse_stream.py` into chunk parsing, executors,
live-run registry, persistence/settlement, and HTTP framing; one durable
heartbeat writer; parse each graph chunk once; load settings once per
execute(); keep compile-once cache and public imports.

Acceptance checks:

- one heartbeat writer/cadence and no heartbeat after terminal;
- compile-once per executor/checkpointer;
- reservation settled exactly once;
- one normalized parse per graph chunk;
- facade imports stay identical;
- resume/cancel/one-terminal/verified-final suites still pass.

Proven:

- Package `smart_rag_api.services.sse` with `chunks.py`, `executors.py`,
  `executor_support.py`, `registry.py`, `service.py`, `service_persist.py`,
  `http.py`, and `constants.py`. `sse_stream.py` is a re-export facade
  including `psycopg` and `true_up_query_reservation`.
- Attach-loop heartbeat writes were removed. Only `_run_heartbeat`
  appends durable heartbeats; `_append` still refuses beats after a
  terminal.
- `LangGraphQueryRunExecutor` loads backend settings once per
  `execute()` and passes that object into summary/assistant persist.
- Module sizes (physical lines): `chunks.py` 72, `executors.py` 542,
  `executor_support.py` 321, `registry.py` 134, `service.py` 485,
  `service_persist.py` 282, `http.py` 78, `sse_stream.py` 51.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run ruff check apps/backend/src/smart_rag_api/services/sse apps/backend/src/smart_rag_api/services/sse_stream.py tests/unit/test_query_sse_executor.py` | 0 | clean |
| `uv run pytest tests/unit/test_query_sse_executor.py tests/unit/test_query_sse_mapping.py tests/unit/test_query_run_sse_trace.py tests/unit/test_query_graph_runtime.py -q` | 0 | passed |
| `APP_ENV=test uv run pytest tests/unit/test_sse_protocol.py tests/contract/test_sse_resume.py -q` | 0 | passed |
| `APP_ENV=test uv run pytest tests/contract/test_sse_heartbeat.py::test_five_held_streams_meet_lag_and_heartbeat_gates -q` | 0 | passed on rerun |

Unverified: first five-stream lag sample on a busy machine was
0.131s p95 against the 0.050s local gate; heartbeat counts still met
the 15s cadence. Rerun passed.

Deviations: persist/support mixins were added so no SSE runtime module
exceeds 600 lines. Settlement tests now patch
`sse.service_persist.true_up_query_reservation`.

Rollback: restore the `sse_stream.py` monolith and dual heartbeat
writers.

Handoff to cleanup packet 7: split `query_admission/service.py` and
`retrieval/hybrid_run.py` without changing SQL ceilings or Hybrid
ordering.
