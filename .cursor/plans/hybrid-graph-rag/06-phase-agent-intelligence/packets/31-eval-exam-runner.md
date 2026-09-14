---
phase: 6
packet: 31
status: complete
title: "Implement the restart-safe production-corpus Hybrid exam runner."
requirement_ids: [P06-31]
---

# Packet 31 — Implement the restart-safe production-corpus Hybrid exam runner.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

Do not add frontend code or HTTP start/poll routes here.

## Preconditions

- P06-10 is **accepted** with production preparation/profile gateway and
  Hybrid rerank/scope/budget bindings proven.
- P06-30 exam tables and claim RPCs exist.
- Inspect query admission, `ProcessHybridRetriever` /
  `RunScopedHybrid`, `score_retrieve_case`, `aggregate_retrieve_gates`,
  `retrieve_gates_pass`, and retrieval-cache bypass hooks.

## Allowed outputs

- Local/test API lifespan exam supervisor (one global runner, case
  concurrency one).
- Runner that claims via database RPC, heartbeats, resumes after crash, and
  scores with existing core metric functions.
- Unit/contract tests for parity, budget, crash/reclaim, cancellation, and
  privacy canaries.
- Runner documentation.

## Forbidden outputs

- `BackgroundTasks` or in-memory lock as durable authority.
- Operator/service-role DSN.
- Evaluator-only `restrict_version_id`.
- Answer, verifier, summary, table, graph, or general-answer nodes.
- Cloning Hybrid ranking into a second implementation.
- Publishing official Recall@10 when any eligible case is unprocessed.
- Mutating process-global retriever budget across Ask and exam.

## Ordered actions

1. Start one bounded supervisor in local/test API lifespan only.
2. Claim queued/expired-running exams through SQL `SKIP LOCKED`.
3. For each ordered case: revalidate caller/ACL/current gold; admit one
   `hybrid` query run on the hidden conversation; bind a per-run
   `QueryRetrieveBudget`.
4. Run accepted P06-10 production preparation with empty memory and requested
   source `company_documents`. Model input is question only.
5. Call existing production Hybrid retrieve with `cache_mode=cold_bypass`
   and no version restriction.
6. Score with `score_retrieve_case` requiring **all** gold IDs in
   `ranked_ids[:10]`. Persist count-only results. True-up the reservation.
7. Aggregate from persisted rows. Official report only when completed count
   equals eligible count.
8. Capture a server-side candidate fingerprint. Qualification fails closed if
   the fingerprint is incomplete.
9. Prove ranked-ID parity against the production Hybrid branch on a frozen
   fixture. Prove no `restrict_version_id`. Canary expected-answer/gold never
   reaches preparation, embedding, rerank, trace, log, or mock arguments.

## Acceptance checks

- Parity fixture: identical ordered `ranked_ids` before scoring.
- Budget exhaustion before and during a case fails closed without a fake
  official report.
- Crash after reservation, after provider call, and after result write
  resumes without duplicate paid work.
- Cancellation settles the active reservation.
- BM25 outage names degradation and forces `gates_pass=false`.

## Negative tests

- Caller role revoked or authorization version changes mid-exam.
- Document ACL downgrade or current-version flip mid-exam.
- Lease reclaim does not duplicate a completed result.
- Incomplete fingerprint blocks qualification.
- Concurrent Ask tests do not mutate exam retriever budgets.

## Stop routes

- Stop if production Hybrid parity cannot be demonstrated without cloning
  ranking.
- Stop if existing query admission cannot be reused.

## Required evidence

- Append runner tests, parity proof, `holdout_opened=false`, budget/true-up
  totals, and P06-32 handoff.
