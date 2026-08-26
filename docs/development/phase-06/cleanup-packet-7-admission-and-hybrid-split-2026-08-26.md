# Cleanup packet 7 — Admission and Hybrid split (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: split `query_admission/service.py` into admit,
reservation, lifecycle, records, usage, and worker-job repositories;
split ceilings into envelopes, retrieve budget, and usage caps; split
`retrieval/hybrid_run.py` into channel execution, budgeted calls,
profile fields, assembly/fallback, and evidence loading, leaving
`HybridRetriever.retrieve` as bounded orchestration.

Acceptance checks:

- public admission/ceiling exports stay identical;
- Python envelopes and usage caps remain synchronized with SQL contracts;
- Hybrid candidate caps, authorization recheck, rerank, fallback reasons,
  model-call ledgers, and result ordering are unchanged;
- no new usage kind, SQL migration, or LightRAG storage refactor.

Proven:

- Package `smart_rag_core.query_admission.repository` with `admit.py`,
  `reservation.py`, `lifecycle.py`, `records.py`, `usage.py`,
  `worker_job.py`, and `errors.py`. `service.py` is a re-export facade.
- Ceilings split: `envelopes.py`, `retrieve_budget.py`, `usage_caps.py`.
  `ceilings.py` remains a re-export facade. Existing
  `query_admission/usage.py` (`execute_counted_model_call`) is unchanged.
- Hybrid retrieve lives under `retrieval/hybrid_run/` so the existing
  `retrieval/hybrid.py` assemble module is not converted into a package.
  Modules: `types.py`, `budget.py`, `profile_fields.py`, `channels.py`,
  `assemble.py`, `evidence.py`, `jobs.py`, `retriever.py`.
- Channel jobs / per-thread DSN / temporal stamps live on
  `HybridChannelJobsMixin` so `retriever.py` stays under 600 lines.
- Package `__init__.py` re-exports public types plus
  `_flatten_channel_candidates` for the existing unit helper lookup.
- Cycle-guard `import smart_rag_core.retrieval.hybrid_run` in query
  nodes remains; removing it is packet 9 / final-gates work.

Module sizes (physical lines): repository `admit` 106, `reservation` 133,
`lifecycle` 166, `records` 212, `usage` 134, `worker_job` 61; ceilings
`envelopes` 146, `retrieve_budget` 94, `usage_caps` 158, `service` 41,
`ceilings` 77; Hybrid `types` 168, `budget` 170, `profile_fields` 147,
`channels` 329, `assemble` 224, `evidence` 109, `jobs` 239,
`retriever` 490.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run ruff check packages/core/src/smart_rag_core/retrieval/hybrid_run packages/core/src/smart_rag_core/query_admission` | 0 | clean |
| `uv run pytest tests/unit/test_query_admission_ceilings.py tests/unit/test_query_reservation_true_up.py -q` | 0 | passed |
| `APP_ENV=test uv run pytest tests/contract/test_query_run_admission.py tests/contract/test_query_admission_api.py -q` | 0 | 15 passed (~144s) |
| `uv run pytest tests/unit/test_hybrid_run.py tests/unit/test_hybrid_fusion.py tests/unit/test_hybrid_rerank.py tests/unit/test_lightrag_query_budget.py -q` | 0 | passed |

Unverified: `tests/contract/test_hybrid_retrieval.py` reached 17 passing
dots then hung for more than 2 minutes on ParadeDB/local Supabase
fixture work and was stopped. Cross-user denial, optimistic versioning,
double-consume, and crash reconciliation remain proven by the admission
contract suite.

Deviations: Hybrid helpers live under `retrieval/hybrid_run/` rather
than `retrieval/hybrid/` because `hybrid.py` already owns
`assemble_hybrid`. RPC usage writes live in `repository/usage.py` to
avoid colliding with `query_admission/usage.py`. Tests that open a
channel DSN now patch `hybrid_run.jobs.psycopg.connect`.

Rollback: restore `query_admission/service.py` and
`retrieval/hybrid_run.py` monoliths.

Handoff to cleanup packet 8: split `query_run_trace.py` and
`evaluation/agent_eval.py` without changing evaluator registry identity
or redaction fields.
