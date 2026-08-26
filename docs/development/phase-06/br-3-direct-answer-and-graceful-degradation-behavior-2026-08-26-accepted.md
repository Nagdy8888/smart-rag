# BR-3 — Direct answer and graceful-degradation behavior (2026-08-26, accepted)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Active canonical packet: amended
[P06-12](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/12-general-chat-execution.md).
The user directed this session to finish every remaining plan todo.

Requirement: greetings and degraded general answers use the general model,
genuine mixed uses deterministic clarification, company no-evidence never
falls back to world knowledge, and `compile_plan` selects explicit
company/general/mixed/invalid graph paths. Direct paths still run
deterministic verification with `evidence_required=False`.

Proven:

- `DETERMINISTIC` / `DETERMINISTIC_CHAT` map to `GENERAL_MODEL`. Canned
  `GREETING_TEXT` is not the live greeting.
- Mixed clarification remains `CLARIFICATION_TEXT`, origin `ambiguous`,
  zero answer calls, empty citations.
- Degraded general answers prefix
  `Company documents were not searched because the question's scope could
  not be established.`
- Company empty evidence stays `insufficient_evidence` / company origin.
- Graph nodes: `company_scope`, `general_scope`, `mixed_scope`,
  `invalid_scope`. `execute_branches` is no longer a graph node name.
- SSE holds `general_scope` / `mixed_scope` drafts until `verify_answer`.
- Verifier model stays off when there are no atomic links.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run pytest tests/unit/test_general_chat_gateway.py tests/unit/test_general_chat_generate.py tests/unit/test_answer_verifier.py tests/unit/test_scope_graph_routes.py` | 0 | 34 passed |
| `uv run pytest tests/unit/test_query_graph_runtime.py tests/unit/test_query_sse_mapping.py tests/unit/test_query_sse_executor.py tests/contract/test_query_preparation.py tests/unit/test_prompt_registry.py` | 0 | 34 passed plus prior suites |
| `uv run pytest tests/unit/test_knowledge_scope.py tests/unit/test_query_routing_matrix.py` | 0 | included in the 101-test BR-3 batch |
| ruff check on generate, graph, nodes, SSE mapper, and BR-3 tests | 0 | import and all-list sorted |

Unverified: live OpenAI greeting/general quality.

Deviations: scope nodes still call existing pipeline implementations.
Cleanup packet 2 owns the file split.

Rollback: restore `DETERMINISTIC_CHAT` canned greeting, linear
`compile_plan → execute_branches` edges, and SSE draft recognition of
`generate_answer` only.

Handoff to cleanup packet 1: record architecture/performance baselines
before splitting `nodes/pipeline.py`.
