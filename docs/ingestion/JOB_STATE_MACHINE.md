---
title: Durable job state machine
owner: engineering-lead
status: draft
last-reviewed: 2026-08-14
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
  dead_letter --> pending: admin retry inserts new job; original DL retained
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

LangGraph checkpoints store compact IDs/tokens/hashes only—never raw bytes, local paths, or secrets. The worker compiles scan/crawl/index/probe graphs with `langgraph-checkpoint-postgres==3.1.2` (`PostgresSaver`) against schema `langgraph` as role `app_checkpointer`. Thread id equals the ingestion `job_id` so a crashed worker resumes the same thread. Runtime never calls `PostgresSaver.setup()`; Phase 2 seeded versions 0–8 and Phase 3 records version 9 (`task_path`, already present). `langgraph.json` module-level graphs remain checkpointer-free so Studio import does not open Postgres.

Dead-letter **retry** (owner/admin `POST /ingestion/jobs/{id}/retry`) creates a **new** ingestion job via `app.retry_ingestion_job`. The original dead-letter row is retained. Failed-but-not-dead-letter jobs (backoff `pending` with `next_attempt_at`, or explicit `failed`) only clear `next_attempt_at` and never wipe `last_error` or `attempt_count`. Members receive 403.

## Public document-version lifecycle

Public `app.document_status` values are orthogonal to queue `job_status`. Internal nodes (normalize, chunk, embed, BM25 verify) are not new public enums.

```mermaid
stateDiagram-v2
  direction LR
  [*] --> uploading: quota reserve
  uploading --> uploaded: finalize quarantine object
  uploading --> [*]: expired quota deletes shell
  uploaded --> scanning: scan_promote claim
  scanning --> parsing: promotion plus hybrid_index
  parsing --> hybrid_ready: canonical plus BM25 verify
  parsing --> failed: terminal ingest failure
  hybrid_ready --> graph_pending: company-visible graph eligible
  hybrid_ready --> graph_ineligible: restricted or ineligible
  hybrid_ready --> deletion_pending: delete or ACL downgrade
  graph_pending --> deletion_pending: delete or ACL downgrade
  graph_ineligible --> deletion_pending: delete or ACL downgrade
  scanning --> failed: malware or scan deny
  uploaded --> failed: admission deny after bytes
```

`GET /ingestion/versions/{version_id}/status` returns the public `status` plus nested diagnostics: scan evidence/age, review/governance, OCR pages, chunk/table counts, embedding ledger, BM25 index version/lag/retry/dead-letter, queue age, and graph-handoff counts. Owner/admin may retry; members receive 403.
