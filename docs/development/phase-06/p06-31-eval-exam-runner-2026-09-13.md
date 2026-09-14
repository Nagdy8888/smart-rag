---
title: P06-31 restart-safe production-corpus Hybrid exam runner
owner: engineering-lead
status: draft
last-reviewed: 2026-09-13
audience: engineering, reviewers, security
---

# P06-31 — Implement the restart-safe production-corpus Hybrid exam runner (2026-09-13)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: implement the restart-safe production-corpus Hybrid exam runner.

User directed continuous execution through P06-36. Work paused 2026-09-10
and resumed 2026-09-13. This packet does not add HTTP start/poll.

## Plan requirement

Quote: implement the restart-safe production-corpus Hybrid exam runner.

Positive checks: ranked-ID parity against the production Hybrid branch on a
frozen fixture; `cache_mode=cold_bypass`; no `restrict_version_id`; all
required gold IDs in `ranked_ids[:10]`; official report only when completed
count equals eligible count; incomplete fingerprint blocks qualification;
`holdout_opened=false`.

Negative checks: budget exhaustion before and during a case; crash resume
skips persisted cases without duplicate paid retrieve; cancellation
true-ups the reservation; BM25 outage forces `gates_pass=false`; stale
gold / missing case / revoked caller; lease reclaim does not double-increment;
exam must not write `query_budget` onto the process Hybrid adapter.

## Files

- [exam_runner.py](../../../packages/core/src/smart_rag_core/evaluation/private_pdf/exam_runner.py)
- [exam_repository.py](../../../packages/core/src/smart_rag_core/evaluation/private_pdf/exam_repository.py)
- [exam_fingerprint.py](../../../packages/core/src/smart_rag_core/evaluation/private_pdf/exam_fingerprint.py)
- [eval_exam_supervisor.py](../../../apps/backend/src/smart_rag_api/services/eval_exam_supervisor.py)
- [main.py](../../../apps/backend/src/smart_rag_api/main.py) lifespan bind
- [cache_store.py](../../../packages/core/src/smart_rag_core/retrieval/cache_store.py) `COLD_BYPASS`
- [retriever.py](../../../packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py) cache bypass
- [adapters_hybrid.py](../../../apps/agents/src/smart_rag_agents/query/runtime/adapters_hybrid.py) cache_mode pass-through
- [test_eval_exam_runner.py](../../../tests/unit/test_eval_exam_runner.py)
- [test_eval_exam_supervisor.py](../../../tests/unit/test_eval_exam_supervisor.py)
- [PDF_EVAL_WORKSPACE.md](../../evaluation/PDF_EVAL_WORKSPACE.md)
- [CONFIGURATION.md](../CONFIGURATION.md)
- [LOCAL_SETUP.md](../LOCAL_SETUP.md)

## Verification

| Command | Exit |
| --- | --- |
| `uv run ruff check` on exam runner/repository/fingerprint, supervisor, and unit tests | 0 |
| `uv run ruff format --check` on those files | 0 |
| `uv run pyright` on those files | 0 errors |
| `uv run pytest tests/unit/test_eval_exam_runner.py tests/unit/test_eval_exam_supervisor.py tests/unit/test_hybrid_retrieval_cache.py tests/unit/test_fastapi_security.py::test_lifespan_binds_offload_executor` | 0; 21 passed |

`holdout_opened=false` in runner status rows. Staging/production eval UI
stays off. Rollback remains `PDF_EVAL_WORKSPACE_ENABLED=false`.

## Proven

- Supervisor starts only when the workspace flag is true, `APP_ENV` is
  local/test, and `SUPABASE_DB_URL` is set. SQL claim is durable authority.
- Cases skip the first `completed_case_count` snapshot IDs. Duplicate persist
  does not increment. Admit reconnects the same reservation.
- Production Hybrid retrieve is called with `cache_mode=cold_bypass` and
  without `restrict_version_id`. Ranking is not cloned.
- Preparation input is the question only, empty memory, and
  `requested_search_scope=company_documents`. Expected answers and gold
  UUIDs are absent from retrieve kwargs.
- Per-run `QueryRetrieveBudget` is bound on `RunScopedHybrid`, not the
  process adapter. A mutated process `query_budget` fails closed.
- Hit definition is every required gold chunk in `ranked_ids[:10]`.
- BM25 outage names `bm25_unavailable` via existing fallback and forces
  `gates_pass=false`. Incomplete qualification fingerprints do not retrieve.
- Cancellation after retrieve skips persist and still true-ups.

## Unverified

- Live `SKIP LOCKED` claim, heartbeat, and reclaim against hosted Postgres.
- Live production-corpus Hybrid ranked-ID parity (unit fixture only).
- HTTP start/poll/cancel/latest/results (P06-32). The lifespan supervisor
  has no examiner until Packet 32 calls `bind_examiner`.
- Managed region/DPA/backup matrix rows. Residual-risk exception from
  P06-27 still applies.

## Handoff

Next packet is
[P06-32](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/32-eval-exam-api.md)
(exam start 202, poll, cancel, latest report, missed cases). Bind the
process Hybrid onto `application.state.eval_exam_hybrid` and call
`bind_examiner(caller)` on start/poll. Do not execute the exam inside the
HTTP request. Do not start P06-11 until P06-28 through P06-36 close.
