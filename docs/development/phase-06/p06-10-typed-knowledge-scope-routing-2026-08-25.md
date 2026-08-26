# P06-10 — Typed knowledge-scope routing (2026-08-25)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: classify `KnowledgeScope` with the approved priority, compile
existing route families plus NoRetrieval answer modes, and copy scope onto
graph state. No answer generation, Studio live, SSE lifecycle, or frontend
edits.

Classification proven:

| Query | Scope | Route / mode |
| --- | --- | --- |
| `Hi` / `Hello` | `general_knowledge` | NoRetrieval / `general_model` |
| `What can you do?` | `general_knowledge` | NoRetrieval / `general_model` |
| capital of France / photosynthesis | `general_knowledge` | NoRetrieval / `general_model` |
| `Rewrite this paragraph: …` | `user_supplied_text` | NoRetrieval / `user_text_model` |
| invoice / `our` / document / table / relationship / summary / graph | `company_documents` | existing matrix; mode `None` |
| `Hi, what is our refund period?` | `company_documents` | Hybrid |
| France + our refund | `ambiguous` | NoRetrieval / `clarification` |
| `Explain monetary policy` | `ambiguous` (no company signal) | NoRetrieval |
| low-confidence / invalid / unavailable model | `ambiguous` | — |
| company + malicious `GENERAL_KNOWLEDGE` | `company_documents` | one forced prep call |
| `Why is the sky blue?` | model `general_knowledge` | exactly one prep call |
| invoice without force | `company_documents` | zero prep calls |

Existing Hybrid/Combined/Table/inspection/media matrix rows remain company
scope with no NoRetrieval mode. Isolated `policy` is not a company signal.

Verification:

| Command | Exit |
| --- | --- |
| `uv run pytest tests/unit/test_knowledge_scope.py tests/unit/test_query_routing_matrix.py tests/contract/test_query_preparation.py tests/unit/test_query_profile.py -q` | 0 |
| `uv run pytest tests/unit/test_knowledge_scope.py tests/unit/test_query_routing_matrix.py tests/unit/test_query_correction.py tests/unit/test_query_profile.py -q` | 0 (71 passed) |
| `uv run ruff check packages/core/src/smart_rag_core/query_routing apps/agents/src/smart_rag_agents/query/state.py tests/unit/test_knowledge_scope.py` | 0 |
| `uv run pyright` on changed routing/state/test files | 0 |

`uv run pyright packages/core/src/smart_rag_core/query_routing` still reports
pre-existing `branches.py` optional-member errors that this packet did not
introduce.

Unverified: live preparation-model scope quality on OpenAI.

Rollback: remove `knowledge_scope.py` and the additive fields, restore
`_extension`/`_needs_model` and the previous `query_profile_v1` hash.

Handoff to P06-11: drain successful LangGraph SSE streams and classify
expected cancellation without hiding real LangSmith errors.
