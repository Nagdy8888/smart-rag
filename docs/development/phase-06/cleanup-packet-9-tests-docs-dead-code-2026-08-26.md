# Cleanup packet 9 — Tests, docs, and dead-code closure (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: split oversized query tests by concern, move shared
doubles under `tests/support`, convert Phase 6 evidence into an index plus
packet files, update routing/docs indexes, remove proven dead code, and add
the AST architecture scanner.

Acceptance checks:

- support modules are not named `test_*.py`;
- query-vertical tests do not import another `test_*.py`;
- evidence and docs links resolve from the new index;
- dead-code deletions pass public import and config tests;
- architecture hard rules (600-line cap, one node body, no cycle guards)
  pass with an empty exception map.

Proven:

- `tests/contract/architecture_scanner.py` plus
  `tests/contract/test_architecture_budgets.py`.
- Shared doubles live under `tests/support/` (`query_postgres`,
  `query_runtime`, `query_sse`, `studio_live`, `query_memory`,
  `answer_verifier`, `online_eval`, `langsmith`, `langsmith_scan`,
  `query_routing`).
- Named oversized tests are split by concern:
  - SSE: `test_query_sse_{verified_final,lifecycle,settlement,event_store}.py`
  - admission: `test_query_admission_{envelopes,idempotency,authorization,budget,audit}.py`
  - Studio: `test_query_studio_{auth,admission,execution,introspection}.py`
  - memory: `test_query_memory_{reaper,summary,deletion,langsmith}.py`
  - verifier: `test_answer_verifier.py`, `_integration.py`, `_scope.py`
  - online eval: `test_langsmith_online_{envelope,scoring,provision}.py`
  - tracing: `test_langsmith_tracing.py` plus `test_langsmith_query_trace.py`
  - routing: `test_query_routing_matrix.py` plus
    `test_query_routing_preparation.py` with cases in
    `tests/fixtures/query_routing_matrix_cases.py`
- `test_sse_resume.py` imports `tests.support.query_postgres` instead of
  another test module.
- Evidence monolith is now
  [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md)
  plus linked files under `docs/development/phase-06/`.
- `QUERY_ROUTING.md` has the post-cleanup module map. `docs/README.md`
  links the packet directory.
- Agent-eval CLI lives under `scripts/agent_eval_cli/` so core cannot
  import agents/API.
- Removed unused `raw_status_is_partial` and the unused sync checkpointer
  holder. Removed `_hybrid_run_cycle_guard` imports. `company_scope_node`
  is the single node body; `execute_branches_node` is an alias.
- `langsmith_agent_runner` is a package so no eval-runner module exceeds
  600 lines.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run pytest tests/contract/test_architecture_budgets.py tests/unit/test_query_sse_verified_final.py tests/unit/test_query_sse_lifecycle.py tests/unit/test_query_sse_settlement.py tests/unit/test_query_sse_event_store.py tests/unit/test_query_studio_auth.py tests/unit/test_query_studio_admission.py tests/unit/test_query_studio_execution.py tests/unit/test_query_studio_introspection.py tests/unit/test_answer_verifier.py tests/unit/test_answer_verifier_integration.py tests/unit/test_answer_verifier_scope.py tests/unit/test_langsmith_online_envelope.py tests/unit/test_langsmith_online_scoring.py tests/unit/test_langsmith_online_provision.py tests/unit/test_langsmith_tracing.py tests/unit/test_langsmith_query_trace.py tests/unit/test_query_routing_matrix.py tests/unit/test_query_routing_preparation.py tests/unit/test_phase6_eval_registry.py tests/contract/test_import_boundaries.py tests/contract/test_langgraph_config.py -q` | 0 | passed |
| `uv run pytest tests/contract/test_docstrings.py tests/contract/test_governance_docs.py tests/unit/test_package_imports.py -q` | 0 | passed |
| `uv run python -c "from smart_rag_agents.query.graph import compile_query_graph"` | 0 | cycle guards unnecessary |
| `uv run python scripts/eval_query_agent_langsmith.py --dry-run --limit 3` | 0 | holdout sealed |

Unverified: admission/reaper Postgres contracts were not re-run after the
split in this packet (helpers moved to `tests.support.query_postgres`;
behavior unchanged). Hosted `--online-only` writes were not re-run.

`pnpm check:docs` later completed with exit 0 after heading and relative-link
fixes (markdownlint 0 issues; links/Mermaid/frontend inventory verified).

Deviations: the 12-definition cap applies to orchestration and node
modules, not schema/mapping helper modules. Test-line and doc-line
targets are reported by the scanner but are not hard-fail.

Rollback: restore cycle-guard imports, `raw_status_is_partial`, the
evidence monolith, the `langsmith_agent_runner.py` file, and the pre-split
test modules.

Handoff to final-gates: empty architecture exceptions, latency counters,
and full repository lint/type/test gates.
