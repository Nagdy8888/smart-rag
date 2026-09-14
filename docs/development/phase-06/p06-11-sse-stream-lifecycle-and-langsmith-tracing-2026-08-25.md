# P06-11 — SSE stream lifecycle and LangSmith tracing (2026-08-25)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: drain successful LangGraph `astream` loops to
`StopAsyncIteration`, call `aclose` only on unfinished streams, classify
expected cancellation without converting `GeneratorExit` into success, and
open a redacted `query.run.sse` parent around complete executor consumption.

Lifecycle proven:

| Fixture | `aclose_count` | `stream_exhausted` | Termination | Settlement |
| --- | --- | --- | --- | --- |
| verified terminal + trailing chunk | 0 | True | `completed` | persist once |
| mid-stream cancel | 1 | False | `cancelled` | none |
| empty verified answer | 0 | True | `error` | none |
| HTTP consumer disconnect | n/a | n/a | background `completed` | resumable |
| stuck executor after cancel | n/a | n/a | hard-cancel after 0.25s | n/a |

Redaction proven: `query.run.sse` parents export correlation IDs, hashed
user, route, and versions only. Query text, JWT, email, API-key, and
passage canaries are absent. Tracing-disabled runs execute the thunk with
no parent. A raised `RuntimeError("graph_failed")` stays an error.

Verification:

| Command | Exit |
| --- | --- |
| `uv run pytest tests/unit/test_query_sse_executor.py tests/unit/test_query_sse_mapping.py tests/unit/test_sse_protocol.py tests/contract/test_sse_resume.py tests/contract/test_sse_heartbeat.py tests/unit/test_query_run_sse_trace.py -q` | 0 (44 passed; `SUPABASE_URL`/`APP_ENV=test` required to collect `create_app` tests) |
| `uv run ruff check` on `sse_stream.py`, `query_run_trace.py`, and the two new/updated unit files | 0 |
| `uv run pyright packages/core/src/smart_rag_core/observability/query_run_trace.py tests/unit/test_query_run_sse_trace.py` | 0 |

`uv run pyright` on `sse_stream.py` and `test_query_sse_executor.py` still
reports pre-existing unused-import, bindings, and older-lambda errors that
this packet did not introduce.

Unverified: live LangSmith UI inspection that completed runs no longer
surface `GeneratorExit` as intended success. Unit/contract proof is
complete; live inspection is deferred to P06-15 and remains blocked without
credentials.

Rollback: restore the previous `execute()` early-return/`aclose` path,
remove `query.run.sse` helpers, and restore the `_run_executor` cancel
`break`.

Handoff to P06-12: implement bounded general/user-text generation with
`answer_origin` and `usage_kind="answer"`.

## 2026-09-13 close-out (resume after P06-36)

Wrapper Packet 11 stayed unchecked while hosted eval packets ran. This
close-out re-ran the packet gates against the split SSE modules. No
lifecycle behavior changed in this run.

Executor drain lives in
`apps/backend/src/smart_rag_api/services/sse/langgraph_execute.py` and
`stream_lifecycle.py`. Recording-stream fixtures live in
`tests/support/query_sse.py`. Lifecycle cases live in
`tests/unit/test_query_sse_lifecycle.py` (the packet’s
`test_query_sse_executor.py` name was retired during the SSE split).
Cancel grace is `CANCEL_GRACE_SECONDS = 0.25`. `_run_executor` wraps
complete consumption in `invoke_traced_query_run_sse` (`query.run.sse`).
`GeneratorExit` is re-raised. `aclose` runs only when the stream did not
exhaust.

2026-09-13 commands (`APP_ENV=test`, `ALLOW_TEST_IDENTITY=true`,
`MOCK_MODEL_MODE=true`):

| Command | Exit |
| --- | --- |
| `uv run pytest tests/unit/test_query_sse_lifecycle.py tests/unit/test_query_sse_mapping.py tests/unit/test_sse_protocol.py tests/contract/test_sse_resume.py tests/contract/test_sse_heartbeat.py tests/unit/test_query_run_sse_trace.py -q` | 0 (all collected tests passed; 1 skipped) |
| `uv run ruff check` on `sse_stream.py`, `langgraph_execute.py`, `stream_lifecycle.py`, `run_orchestration.py`, `query_run_trace.py`, `test_query_sse_lifecycle.py`, `test_query_run_sse_trace.py` | 0 |
| `uv run pyright packages/core/src/smart_rag_core/observability/query_run_trace.py tests/unit/test_query_run_sse_trace.py` | 0 |

Live LangSmith UI inspection that completed runs no longer show
`GeneratorExit` as intended success remains **blocked** (no browser
LangSmith session). Unit/contract proof stands. Do not treat mocked
spans as UI proof.

Handoff to P06-12 remains: bounded general/user-text generation is next
in the wrapper order.
