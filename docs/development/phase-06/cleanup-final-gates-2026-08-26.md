# Cleanup final-gates — Architecture, work counts, and repository gates (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: prove architecture budgets with an empty exception
map, record remaining 400/500/300-line targets as non-exceptions, measure
deterministic work and mocked compile timing against the packet 1
baseline, and run full repository format/lint/type/docs gates.

Acceptance checks:

- `ARCHITECTURE_EXCEPTIONS` is empty;
- hard architecture rules pass;
- general/greeting/user-text skip retrieval, correction, fusion, tables,
  optional tools, and verifier-model work;
- mixed clarification also skips the answer model;
- company routes retain retrieve → correction → verify;
- compile reuse remains the SSE/executor design, not a global deps
  registry;
- remaining line-count targets are listed, not waived.

Proven:

- Hard architecture scan is empty. No cycle guards, no cross-test
  `test_*.py` imports, no 600-line production modules, one exported
  `*_node` body per node module.
- Work counters from `_visit_nodes` (mock mode):

  | Path | Hybrid calls | Visited nodes |
  | --- | ---: | --- |
  | `Hello` | 0 | `enforce_admission`, `load_memory`, `prepare_query`, `compile_plan`, `general_scope`, `verify_answer` |
  | `What is the capital of France?` | 0 | same general path |
  | `What is our refund period?` | 1 | company path through `company_scope` → `apply_correction` → `fuse_evidence` → `compose_tables` → `disclose_optional_tools` → `generate_answer` → `verify_answer` |
  | genuine mixed (`France` and refund) | 0 | `enforce_admission`, `load_memory`, `prepare_query`, `compile_plan`, `mixed_scope`, `verify_answer` |

- `test_mixed_scope_leaves_usage_counters_unchanged` keeps
  `answer_call_count == 0` and `verifier_call_count == 0`.
- `compile_query_graph()` after warmup: p50 12.489 ms, p95 15.721 ms
  (50 runs). Packet 1 baseline was first 9.3 ms / second 12.4 ms with no
  process cache. The factory still compiles per call; reuse is the
  executor/checkpointer compile-once path proven by
  `test_query_graph_compile_reuse.py` and
  `test_executor_compiles_once_per_checkpointer`.
- Cold import (`python -X importtime`):
  `smart_rag_agents.query.graph` cumulative 2.986 s. Informational only.
- Do not claim latency improvement from line-count reduction. The
  deterministic win is skipped company nodes and zero Hybrid on
  general/mixed.

Remaining 400-line production targets (not exceptions):
`graph.py` 474, `runtime/adapters.py` 538, `studio/live_admission.py` 407,
`sse/executors.py` 528, `sse/service.py` 481, `query_profile/metrics.py` 424,
`knowledge_scope.py` 506, `matrix_rules.py` 545, `preparation.py` 422,
`hybrid_run/retriever.py` 490, `agent_eval/mapping.py` 537,
`agent_eval_cli/runtime.py` 411, `langsmith_agent_runner/evaluate.py` 483,
`online_envelope.py` 417.

Remaining 500-line test targets: `test_hybrid_run.py` 939,
`test_knowledge_scope.py` 505, `test_langsmith_agent_runner.py` 581,
`test_query_graph_runtime.py` 550.

Remaining 300-line doc target: `LANGSMITH_TRACING.md` 328.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run pytest tests/unit/test_scope_graph_routes.py tests/unit/test_query_graph_compile_reuse.py tests/contract/test_architecture_budgets.py tests/contract/test_import_boundaries.py -q` | 0 | passed |
| `uv run ruff check` on query-vertical roots | 0 | clean |
| `pnpm check:docs` | 0 | markdownlint 0; links/Mermaid/frontend inventory verified |
| `uv run python scripts/ci/check_pyright_baseline.py` | 1 | Pyright error count 679 vs baseline 0 |
| `uv run ruff format --check .` | 1 | unformatted files remain in the dirty tree, including unrelated apps |

Unverified: full-repository `uv run pyright` and `pnpm check:fast` were
not claimed green. Query-vertical Pyright still reports LangGraph
`Runtime[QueryGraphContext]` `add_node` stub mismatches and
`hybrid_run` intra-package `_private` helper visibility. Hosted
LangSmith and ParadeDB hybrid contracts were not re-run. Admission
Postgres contracts were not re-run after the packet 9 test split.

Deviations: 400/500/300-line targets remain visible and are not
`ARCHITECTURE_EXCEPTIONS`. Full-repo format/type gates are blocked by
the pre-existing dirty tree plus split-module private-helper typing.

Rollback: none for measurements. Architecture scanner and split tests
roll back with packet 9.

Handoff: plan todos `tests-docs-dead-code` and `final-gates` are
evidenced. Phase 6 wrapper completion still requires user acceptance
of this exit record.
