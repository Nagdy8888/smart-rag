# P06-12 — General and user-text execution (2026-08-25)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: add a no-source `general_chat_v1` path that counts as
`usage_kind="answer"`, set `answer_origin` on every new answer, and keep
company grounding unchanged.

Prompt: `general_chat_v1` SHA-256
`b920c67bb472daa5cb5338d15025711cd5f9d4e94e9abfabda01216668a97d51`.
Reuses `ANSWER_MODEL_ID=gpt-4o-mini`. No new usage kind or migration.

Origin matrix:

| Query | Origin | Model calls | Citations |
| --- | --- | --- | --- |
| `Hi` | `general_knowledge` | 2 (`profile` + `answer`) | none |
| `How can you help me?` | `general_knowledge` | 1 (`answer`) | none |
| capital of France | `general_knowledge` | 1 | none |
| rewrite supplied text | `user_supplied_text` | 1 | none |
| mixed France + refund | `ambiguous` | 0 | none |
| company, no evidence | `company_documents` | 0 | refusal |
| company with evidence | `company_documents` | existing RAG | cited |

SSE: additive `answer_origin` (`origin` field) before `token_delta`; schema
major version stays `1`. Historical/null payloads emit no origin event.
Mock general chat performs no DNS. Document-access claims are refused, not
stripped. A second generation still raises `second_answer_generation`.

Verification:

| Command | Exit |
| --- | --- |
| `uv run pytest tests/unit/test_general_chat_gateway.py tests/unit/test_general_chat_generate.py tests/unit/test_answer_verifier.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_sse_mapping.py tests/unit/test_prompt_registry.py -q` | 0 (52 passed) |
| `uv run ruff check` on gateways, query_answer, prompts, query nodes, `query_graph_runtime.py` | 0 |
| `uv run pyright` on `openai_general_chat.py`, `generate.py`, `models.py`, `schemas.py`, `versions.py` | 0 |

`uv run pyright` on the full `query/` and `query_graph_runtime.py` trees
still reports pre-existing checkpointer/bindings errors this packet did not
introduce.

Rollback: remove `general_chat_v1`, `openai_general_chat.py`,
`answer_origin`, and the general-chat gateway/node branches.

Handoff to P06-13: add authenticated `query_studio_live` without changing
unbound `query_studio`.

## 2026-09-13 close-out (resume after P06-36)

Wrapper Packet 12 stayed unchecked while hosted eval packets ran. This
close-out re-ran the packet gates. No general-chat contract changed.

`general_chat_v1`, `openai_general_chat.py`, `answer_origin`, and
`usage_kind="answer"` remain in place. Company grounding and
`filter_invented_ids` are unchanged. Mock mode performs no DNS.

2026-09-13 commands (`APP_ENV=test`, `ALLOW_TEST_IDENTITY=true`,
`MOCK_MODEL_MODE=true`):

| Command | Exit |
| --- | --- |
| `uv run pytest tests/unit/test_general_chat_gateway.py tests/unit/test_general_chat_generate.py tests/unit/test_answer_verifier.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_sse_mapping.py tests/unit/test_prompt_registry.py -q` | 0 |
| `uv run ruff check` on gateways, query_answer, prompts, query, `query_graph_runtime.py` | 0 |
| `uv run pyright packages/core/src/smart_rag_core/gateways/openai_general_chat.py packages/core/src/smart_rag_core/query_answer` | 0 |

Handoff to P06-13: authenticated `query_studio_live`.

## 2026-08-26 tracing latency repair

Observed run `38aed2cd-b1bb-4f2c-8761-13c478669a68` completed in
144.56 seconds even though query profiling took 3.49 seconds and the
general-chat OpenAI request took 2.33 seconds. The remaining 121.25-second
gap followed the model response.

Two tracing defects formed the causal chain:

1. `process_outputs` received the adapter's raw four-item tuple, while
   `redact_rerank_call_outputs` assumed a mapping and raised
   `AttributeError("'tuple' object has no attribute 'get'")`. The affected
   profile/general-chat spans remained unfinished.
2. Query gateway and SSE `finally` blocks called a newly constructed
   `Client().flush()` with the pinned SDK default `timeout=None`. That is an
   unbounded synchronous queue wait outside the admitted run deadline.

The repaired redactor accepts both raw tuples and mapping wrappers, exports
only request id, token counts, and payload key names, and tolerates malformed
usage fields without preventing span closure. Gateway, retrieval, and SSE
request paths no longer drain LangSmith. The SDK background queue exports
normally; backend shutdown alone drains the process-cached client with a
two-second maximum. Tracing failure cannot delay or fail answer delivery.

Focused verification:

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit/test_general_chat_gateway.py tests/unit/test_general_chat_generate.py tests/unit/test_answer_verifier.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_sse_mapping.py tests/unit/test_prompt_registry.py tests/unit/test_langsmith_tracing.py tests/unit/test_query_run_sse_trace.py tests/unit/test_async_bridge.py tests/unit/test_query_admission_ceilings.py tests/unit/test_query_reservation_true_up.py -q` | 112 passed |
| `uv run ruff check packages/core/src/smart_rag_core/observability/langsmith_tracing.py packages/core/src/smart_rag_core/observability/query_trace/sse.py packages/core/src/smart_rag_core/runtime/async_bridge.py apps/agents/src/smart_rag_agents/query/gateway/sync_bridge.py apps/agents/src/smart_rag_agents/query/gateway/__init__.py apps/backend/src/smart_rag_api/main.py tests/unit/test_langsmith_tracing.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_run_sse_trace.py tests/unit/test_async_bridge.py` | passed |
| `uv run pyright packages/core/src/smart_rag_core/observability/langsmith_tracing.py apps/agents/src/smart_rag_agents/query/gateway/sync_bridge.py apps/agents/src/smart_rag_agents/query/gateway/__init__.py apps/backend/src/smart_rag_api/main.py` | 0 errors |
| `uv run python scripts/check.py --tier docs` | passed |

After rebuilding the API image, a live OpenAI greeting probe through the
production profile and general-chat gateway bridges measured 2.768 seconds
for profiling, 1.511 seconds for answer generation, and 4.280 seconds total.
The answer was `general_knowledge`, complete, uncited, and used 240 prompt /
22 completion tokens. LangSmith then showed all three new provider spans
closed with no errors: query profile 2.758 seconds and general chat 1.506 /
2.914 seconds. No tuple-processing warning or post-model 121-second gap
recurred.

An authenticated HTTP/SSE timing run was not issued because no developer JWT
was configured in the rebuilt container. The live provider, trace closure,
and exact synchronous bridge were exercised; the user-facing authenticated
transport remains a follow-up smoke check, not a claimed result.

The full multi-file Pyright invocation still reports pre-existing private-use,
legacy bridge generic, and test-fixture protocol diagnostics outside this
repair. No migration, usage-kind, model, prompt, route, citation, or grounding
contract changed. Rollback is the code revert; disabling
`LANGSMITH_TRACING` remains the operational kill switch.

## 2026-08-26 run-row lock stall repair

The LangSmith-only explanation above is incomplete. After the flush repair,
a live profile+general gateway probe was 4.28s, but authenticated UI run
`c31e50dc-02cb-4aa8-aac9-dbb8de5baafa` still took ~145s. LangSmith child
spans closed the general-chat model in 1.51s. The `general_scope` chain
span stayed open until 12:56:43.224Z.

Postgres logs for that window show `append_run_event` waiting on
`SELECT * FROM app.runs … FOR UPDATE` from 12:54:42.901Z, then
`canceling statement due to statement timeout` at 12:56:42.901Z (exactly
120s). The `general_scope` checkpoint was written 326ms later. No
LangSmith HTTP child span or API LangSmith error appears. The waiter was
the 15s heartbeat on the asyncio loop; the holder was the graph
connection's uncommitted `llm_usage` KEY SHARE. `SET ROLE app_api` did
not apply the 2s `lock_timeout`, so the wait used the login-role 120s
statement timeout.

Repair:

- Heartbeat and executor appends use `asyncio.to_thread`.
- `PostgresRunEventStore` sets `SET ROLE app_api` and
  `SET LOCAL lock_timeout TO '2s'` in one parameter-free statement on
  every transaction. Autocommit stays off.
- Append failures emit sanitized `sse.append_failed` logs (`run_id`,
  type, SQLSTATE/reason, elapsed seconds). Heartbeats degrade; status
  and terminal None-return semantics are unchanged.
- `execute_counted_model_call` still does not commit. Crash-before-send
  must keep consume uncommitted so true-up can release $0. Offload plus
  lock-timeout close the loop deadlock without broadening reservation
  durability.

Authenticated live HTTP/SSE timing after this repair is **not** claimed.

Focused verification:

| Command | Result |
| --- | --- |
| `APP_ENV=test ALLOW_TEST_IDENTITY=true pytest tests/unit/test_query_sse_event_store.py tests/unit/test_query_sse_lifecycle.py tests/unit/test_sse_protocol.py tests/contract/test_sse_heartbeat.py tests/contract/test_sse_resume.py tests/contract/test_sse_run_lock.py -q` | 36 passed |
| `pytest tests/contract/test_query_admission_budget.py::test_crash_before_and_after_send_and_double_true_up -p tests.support.query_postgres -q` | 1 passed |
| `ruff check` on `sse/store.py`, `sse/service.py`, `sse/service_persist.py`, and the new tests | passed |
| `pyright` on `sse/store.py`, `sse/service.py`, `sse/service_persist.py` | 0 errors |
| `uv run python scripts/check.py --tier docs` | passed |

No migration, usage kind, model, prompt, route, citation, or grounding
contract changed. Rollback is the code revert. Disabling LangSmith
tracing is not the operational fix for this stall.
