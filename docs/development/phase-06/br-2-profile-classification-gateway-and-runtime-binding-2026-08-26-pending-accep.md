# BR-2 — Profile classification gateway and runtime binding (2026-08-26, pending acceptance)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Active canonical packet: amended [P06-10](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/10-knowledge-scope-routing.md).
Coding packet from
[scope_graph_nodes_916779e1.plan.md](../../../.cursor/plans/scope_graph_nodes_916779e1.plan.md).
The user asked to implement that plan in this session after BR-1A drafted
the four decisions. BR-3 and cleanup packets 1–9 were not started.

Requirement: one counted `usage_kind="profile"` call when remaining
natural-language scope needs the model; mock and live adapters; FastAPI/
Studio live binding; typed `ScopeDegradationReason` instead of false
ambiguity. `query_profile_v1.md` body and SHA stay frozen.

Classification fixtures:

| Query | Scope | Degradation | Model calls |
| --- | --- | --- | --- |
| `Hi` / `hi my friend` without caller | `general_knowledge` | `profile_unavailable` | 0 |
| `hi my friend` with bound caller | `general_knowledge` | none | 1 |
| `how are you?` / `what's up` / `nice to meet you` | `general_knowledge` | unavailable unless caller | 1 when bound |
| `مرحبا` / `السلام عليكم` / `أهلا` / `hi 👋` | greeting; requires profile | unavailable unless caller | 1 when bound |
| `What can you do?` / `who are you` | `general_knowledge` | none | 0 |
| capital of France / photosynthesis | `general_knowledge` | none | 0 |
| `What is the capital of Japan?` | `general_knowledge` | unavailable unless caller | 1 when bound |
| `Rewrite this paragraph: …` | `user_supplied_text` | none | 0 |
| invoice / `our` / document / table / relationship / summary / graph | `company_documents` | none | 0 |
| `Hi, what is our refund period?` | `company_documents` | none | 0 |
| greeting after cited company memory | `general_knowledge` | unavailable unless caller | 1 when bound |
| unresolved follow-up after cited memory | `company_documents` | none | 0 |
| France + our refund | `ambiguous` | none | 0 |
| `Explain monetary policy` | `general_knowledge` | `profile_unavailable` | 0 |
| model confidence `0.79` | `general_knowledge` | `profile_low_confidence` | 1 |
| invalid / extra `scope_degradation_reason` | `general_knowledge` | `profile_malformed` | 1 |
| company + malicious `GENERAL_KNOWLEDGE` | `company_documents` | none | 1 when forced |

Profile adapter / runtime safety:

- Live adapter: `store=False`, `max_retries=0`, strict `json_schema`, no
  tools, allow-list `gpt-4o-mini` only, prompt version/SHA verified.
- Mock adapter: no DNS, no OpenAI client, schema-valid payload, no
  degradation field.
- `query_profile_json_schema()` forbids extra fields and a fourth
  subquestion; five `KnowledgeScope` values only.
- FastAPI/live Studio bind `QueryGraphDeps.model_caller` and
  `profile_model_id="gpt-4o-mini"`. Local `query_studio` stays unbound.
- LangSmith `openai.responses.query_profile` and `model.query_profile`
  hash `user_query` / `recent_memory`; they do not copy raw text.
- `query_profile_v1` SHA
  `5a969a9d83d8716c6033fc1a7c5a773e5e63896953af3847d4e85216425e9e1f`
  unchanged.

Existing Hybrid/Combined/Table/inspection/media matrix rows remain
company scope with `no_retrieval_answer_mode=None`. General, degraded
general, user-text, and genuine mixed plans stay NoRetrieval with
`company_claim_forbidden=True`.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run pytest tests/unit/test_knowledge_scope.py tests/unit/test_query_profile.py tests/unit/test_query_profile_gateway.py` | 0 | 38 passed |
| `uv run pytest tests/unit/test_model_gateway.py tests/unit/test_prompt_registry.py tests/unit/test_langsmith_tracing.py` | 0 | 26 passed |
| `uv run pytest tests/unit/test_knowledge_scope.py tests/unit/test_query_routing_matrix.py tests/contract/test_query_preparation.py` | 0 | 61 passed |
| `uv run pytest tests/contract/test_query_preparation.py tests/unit/test_query_routing_matrix.py tests/unit/test_query_correction.py tests/contract/test_langgraph_config.py` | 0 | 56 passed |
| `uv run pytest tests/unit/test_query_studio_live.py tests/unit/test_query_graph_runtime.py` | 0 | 34 passed |
| `uv run ruff check` on routing, profile, gateways, state, live runtime, and BR-2 tests | 0 | all checks passed |
| `uv run pyright` on BR-2 owned files listed below | 0 | 0 errors |

Pyright owned files: `knowledge_scope.py`, `signals.py`, `preparation.py`,
`models.py`, `matrix.py`, `query_routing/__init__.py`,
`query_profile/schemas.py`, `query_profile/versions.py`,
`gateways/openai_profile.py`, `query/state.py`, `query/live_runtime.py`,
`test_knowledge_scope.py`, `test_query_profile_gateway.py`.
`uv run pyright packages/core/src/smart_rag_core/query_routing` still
reports pre-existing `branches.py` optional-member errors. Whole
`apps/agents/src/smart_rag_agents/query` still reports pre-existing
checkpointer/studio/pipeline errors this packet did not introduce.

Proven: greetings/small talk require the one profile call and cannot be
hijacked by cited company memory; company signals skip the profile call
and override a malicious general payload; isolated `policy` is not a
company signal; unavailable/malformed/low-confidence profile is typed
general degradation, not `AMBIGUOUS`; mock mode performs no network;
live pins and actual model id are bound; Hybrid/Combined/Table rows are
unchanged.

Unverified: live OpenAI profile classification quality; explicit user
acceptance of BR-2.

Deviations:

- `QueryProfileModelResponse.inferred` remains for existing offline
  `test_query_profile.py` callers.
- `ModelGatewayUnavailableError` is imported inside `prepare_query` so
  `gateways.model` does not circular-import `query_routing`.
- Provider/timeout failures that `_run_coro` wraps as `AnswerError`
  become `profile_unavailable`. Local payload validation still records
  `profile_malformed`.
- Answer framing, citation sanitizer, and graph-topology nodes remain
  BR-3 / later cleanup packets.

Rollback: restore greeting early-return/`_needs_model` bail-out, remove
`ScopeDegradationReason` and profile transport/adapter/runtime fields,
and keep `query_profile_v1` SHA unchanged. Do not start BR-3 until the
user accepts this packet.

Handoff to BR-3 (amended P06-12): implement direct-answer and
graceful-degradation behavior, greeting/general call ledgers, mixed
clarification with zero answer calls, and deterministic verification on
direct paths. Do not start cleanup packets 1–9 in the same run.
