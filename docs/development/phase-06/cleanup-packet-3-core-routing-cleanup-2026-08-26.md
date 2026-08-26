# Cleanup packet 3 — Core routing cleanup (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: split `branches.py`, convert `matrix.py` into a thin
compiler over ordered named rules, convert `models.py` into a package
with stable re-exports, snapshot plans before/after, and keep
`hybrid_run` cycle guards until cold-import tests prove they are
unnecessary.

Acceptance checks:

- representative RetrievalPlan JSON dumps match pre-split fixtures;
- named-rule precedence matches the repository order;
- Hybrid/Combined/Table/inspection/refusal/NoRetrieval behavior is
  unchanged;
- `from smart_rag_core.query_routing.models import X` still works;
- import-cycle guards remain.

Proven:

- Models live in `query_routing/models/{plan,preparation,results}.py`.
- Branch execution lives in `protocols.py`, `acl_blindness.py`,
  `retrieve_budget.py`, `branch_results.py`, `branch_scheduler.py`, and
  `branch_channels/{hybrid,graph,table,citation}.py`. `branches.py` is a
  re-export facade.
- Matrix rules are the immutable `MATRIX_RULES` tuple in
  `matrix_rules.py`. `compile_retrieval_plan` remains the public compiler.
- Pre-split fixtures:
  `tests/fixtures/query_routing/plan_snapshots.json`.
- `assemble.py` imports `BranchKind` from `models.plan` and `BranchResult`
  only under `TYPE_CHECKING` so the models package can import fusion
  passage types.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run ruff check packages/core/src/smart_rag_core/query_routing` | 0 | clean |
| `uv run pytest tests/unit/test_query_routing_matrix.py tests/unit/test_routing_plan_snapshots.py tests/unit/test_matrix_rule_precedence.py tests/unit/test_query_branches_citations.py tests/unit/test_query_correction.py tests/unit/test_query_retrieve_state_sync.py tests/unit/test_phase6_querytype_map.py tests/unit/test_lightrag_query_budget.py tests/unit/test_hybrid_run.py tests/contract/test_query_preparation.py tests/contract/test_import_boundaries.py tests/contract/test_docstrings.py` | 0 | passed |

Unverified: removing `hybrid_run` import-order guards. They stay.

Deviations: none on routing outputs. Fusion assemble import path was
narrowed to break the new models-package cycle.

Rollback: restore `models.py` / `branches.py` / `matrix.py` monoliths and
the pre-split assemble import.

Handoff to cleanup packet 4: split `gateways/model.py` and
`query_answer/generate.py` without changing prompt SHA, call accounting,
or answer origins.
