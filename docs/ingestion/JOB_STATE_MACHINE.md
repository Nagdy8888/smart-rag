---
title: Durable job state machine
owner: engineering-lead
status: draft
last-reviewed: 2026-08-13
audience: engineering
---

# Durable job state machine

State transitions for Phase 3 durable queues: ingestion, BM25 projection, LightRAG graph handoff, deletion/ACL cleanup, and dead-letter handling. Queue authority is Supabase Postgres only; Valkey is never authoritative.

Related: [INGESTION_LIMITS.md](./INGESTION_LIMITS.md) · [Phase 3 evidence](../development/phase-03-ingestion-evidence.md)

## Shared lifecycle

All primary queue tables (`app.ingestion_jobs`, `app.bm25_index_jobs`, `app.lightrag_index_jobs`) share `app.job_status` and lease columns documented in Phase 2.

```mermaid
stateDiagram-v2
  direction LR
  [*] --> pending: enqueue idempotent
  pending --> processing: claim SKIP LOCKED
  processing --> processing: heartbeat renew
  processing --> completed: complete valid lease
  processing --> pending: fail transient backoff
  processing --> failed: fail permanent
  processing --> pending: reclaim expired lease
  processing --> cancelled: cancel valid lease
  pending --> cancelled: cancel before claim
  failed --> pending: bounded replay
  failed --> dead_letter: max attempts exhausted
  processing --> dead_letter: max attempts on terminal fail
  dead_letter --> pending: admin replay new idempotency key
  completed --> [*]
  cancelled --> [*]
  dead_letter --> [*]: evidence retained
```

## Priority bands

| Priority | Typical workloads |
| --- | --- |
| `critical` | Security cleanup, legal hold, forced deletion |
| `high` | Deletion/ACL BM25 purge, graph ACL remove |
| `normal` | Scan/parse/chunk/embed, BM25 upsert, graph index handoff |
| `low` | Reconciliation, deferred rebuild batches |

Claims order `critical` → `high` → `normal` → `low`, then age (`created_at`), then `estimated_size_bytes`.

## Ingestion jobs

```mermaid
stateDiagram-v2
  direction TB
  state "pending (normal/high)" as ing_pending
  state "processing (leased)" as ing_proc
  state "completed" as ing_done
  state "dead_letter" as ing_dl

  [*] --> ing_pending: admission OK pending less than 100
  ing_pending --> ing_proc: worker claim
  ing_proc --> ing_done: graph/worker complete
  ing_proc --> ing_pending: transient fail plus backoff
  ing_proc --> ing_dl: attempts exhausted
  ing_dl --> ing_pending: replay traceable attempt
```

Admission rejects enqueue when pending ingestion jobs ≥ **100** or daily ingestion budget reservation fails.

## BM25 index jobs

```mermaid
stateDiagram-v2
  direction TB
  state "pending upsert/delete" as bm25_pending
  state "processing" as bm25_proc
  state "completed" as bm25_done

  [*] --> bm25_pending: canonical chunk/version enqueue
  bm25_pending --> bm25_proc: worker claim high priority deletes first
  bm25_proc --> bm25_done: ParadeDB projection verified
  bm25_proc --> bm25_pending: transient fail
```

## Graph handoff (LightRAG index jobs)

Phase 3 stops at durable `Graph Pending` handoff; Phase 5 owns graph mutation.

```mermaid
stateDiagram-v2
  direction TB
  state "pending index" as lr_index
  state "pending remove/acl/rebuild" as lr_maint
  state "processing" as lr_proc
  state "completed handoff" as lr_done

  [*] --> lr_index: Hybrid Ready plus graph eligible
  [*] --> lr_maint: deletion or ACL cleanup
  lr_index --> lr_proc: claim when pending index less than or equal 50
  lr_maint --> lr_proc: claim always allowed
  lr_proc --> lr_done: handoff recorded
  note right of lr_index
    When pending index greater than 50,
    new index claims pause;
    maintenance ops continue.
  end note
```

## Dead-letter queue

`app.dead_letter_jobs` preserves terminal failure evidence. Replay creates a **new** primary-queue row with a fresh `idempotency_key` and `payload_ref.replay_of` pointing at the dead-letter/source job. Original dead-letter rows are never deleted by replay.

## Side-effect ledger

`app.job_operation_ledger` dedupes graph/worker side effects by `(job_table, job_id, operation_key)`. Valid writes require a non-expired lease token on the owning job row. Lease loss or cancellation blocks new ledger inserts.

## Checkpointer boundary

LangGraph checkpoints store compact IDs/tokens/hashes only—never raw bytes, local paths, or secrets. Phase 3 probe graph uses in-memory checkpointer because `langgraph-checkpoint-postgres` is not yet pinned; production wiring follows the Phase 2 bootstrap migration in `langgraph` schema without runtime auto-migrate.
