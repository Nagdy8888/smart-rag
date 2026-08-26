# Cleanup packet 2 — Explicit scope nodes and agent node split (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: replace `nodes/pipeline.py` with cohesive node
modules; move gateway bridges, codecs, tokens, and guards; keep explicit
company/general/mixed/invalid scope nodes; keep topology construction
separate; prove direct paths skip retrieve/tools and that Studio uses
the same router.

Acceptance checks:

- `pipeline.py` is gone and has no required callers;
- general/greeting/user-text invoke no retriever or optional tool;
- mixed invokes no retrieval or answer model;
- company/inspection/refusal remain on the company path;
- SSE still holds drafts until `verify_answer`;
- local/live Studio register the same scope nodes.

Proven:

- Node implementations live in `nodes/memory.py`, `prepare.py`,
  `plan.py`, `company_scope.py`, `general_scope.py`, `mixed_scope.py`,
  `invalid_scope.py`, `correction.py`, `fusion.py`, `tables.py`,
  `answer.py`, `verify.py`, `admission.py`, plus `shared.py`,
  `state_codec.py`, and `tokens.py`.
- Gateway helpers live in `query/gateway/{sync_bridge,answer,general_chat,verifier}.py`.
- Routers live in `nodes/topology.py`. `graph.py` re-exports
  `_route_after_*` aliases for existing tests.
- Instrumented graph streams prove general/mixed skip company-only
  nodes and Hybrid retrieve. Mixed leaves usage counters unchanged.
- Studio local/live graphs register the same scope nodes and omit
  `execute_branches`.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run ruff check apps/agents/src/smart_rag_agents/query tests/unit/test_scope_graph_routes.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_retrieve_state_sync.py` | 0 | clean |
| `uv run pytest tests/unit/test_scope_graph_routes.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_retrieve_state_sync.py tests/unit/test_knowledge_scope.py tests/unit/test_query_routing_matrix.py tests/unit/test_query_correction.py` | 0 | passed |
| `uv run pytest tests/unit/test_general_chat_generate.py tests/unit/test_answer_verifier.py tests/unit/test_query_sse_mapping.py tests/unit/test_query_studio.py tests/unit/test_query_studio_live.py tests/contract/test_langgraph_config.py tests/contract/test_import_boundaries.py tests/contract/test_docstrings.py` | 0 | passed |

Unverified: live OpenAI greeting/general quality; `pnpm check:fast`.

Deviations: `execute_branches_node` remains as a shared helper inside
`company_scope.py` rather than a graph node. `generate_answer_node`
remains the shared draft implementation used by general/mixed scope
nodes.

Rollback: restore `nodes/pipeline.py` and the previous import sites.

Handoff to cleanup packet 3: split `query_routing` branches, matrix
rules, and models after snapshotting plan/branch fixtures.
