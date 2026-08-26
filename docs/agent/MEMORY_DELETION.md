---
title: Conversation memory, retention, and immediate deletion
owner: engineering-lead
status: draft
last-reviewed: 2026-08-16
audience: engineering, security
---

# Conversation memory, retention, and immediate deletion

Phase 6 packet 7: LangGraph checkpoints/store, dedicated 7/30-day reaper,
and immediate conversation deletion. Retention windows never delay an
explicit delete.

Related: [QUERY_ADMISSION.md](./QUERY_ADMISSION.md) ·
[SSE.md](../api/SSE.md) ·
[FASTAPI_SECURITY.md](../api/FASTAPI_SECURITY.md) ·
[PHASE6_EVAL_REGISTRY.md](../evaluation/PHASE6_EVAL_REGISTRY.md) ·
[LANGSMITH_TRACING.md](../development/LANGSMITH_TRACING.md) ·
[OPENAI_DATA_GOVERNANCE.md](../security/OPENAI_DATA_GOVERNANCE.md)

## Checkpoints and store

- Query runtime compiles with `compile_query_graph(checkpointer=...)`.
  `thread_id` is `str(conversation_id)`. Module-level Studio `graph` stays
  checkpointer-free.
- Checkpointer role is `app_checkpointer` on schema `langgraph`. Runtime
  never calls `PostgresSaver.setup()` or `PostgresStore.setup()`.
- Checkpoints persist compact state: source `passage` / `snippet` / `html` /
  `citation_text` bodies become hashes and character counts. Raw files are
  never stored.
- LangGraph store (`langgraph.store`) holds compact summaries and
  preferences only. Namespace is
  `(company_id or "company", user_id, conversation_id)`. Writes with
  `passage` / `snippet` / `html` / `source` keys fail closed.
- Summary generation is a counted gateway call (`usage_kind=summary`). If
  the run envelope cannot cover the cap, the write is skipped and recorded
  as `summary_deferred`.
- Deleted-source citations are marked `unavailable` on the citation row.
  Historical messages are not rewritten.

## Immediate deletion

`DELETE /conversations/{conversation_id}` is HTTP 204 for the creator or
an owner/admin. Foreign or already-tombstoned conversations are HTTP 404.

```mermaid
flowchart TD
  req["DELETE /conversations/{id}"] --> auth{Creator or owner/admin?}
  auth -->|no| notFound["404 not_found"]
  auth -->|yes| tombstone["SET conversations.deleted_at"]
  tombstone --> cascade["Delete messages, runs, events, citations, private feedback"]
  cascade --> ckpt["Delete langgraph.checkpoints* where thread_id = conversation_id"]
  ckpt --> store["Delete langgraph.store rows whose prefix contains conversation_id"]
  store --> audit["Content-free audit event plus LangSmith deletion request"]
  audit --> deny["Every read/resume path 404s on tombstone"]
```

One Postgres transaction (`app.delete_conversation`) tombstones first, then
purges conversation-scoped rows. `app.search_conversation_lingering_ids`
must return zero matches for messages, runs, events, citations, private
feedback, checkpoints, and store namespaces. Tombstone row, content-free
audit, and pseudonymized aggregate `llm_usage` may remain.

LangSmith cloud deletion is **not** claimed. The transaction inserts
`app.langsmith_deletion_requests` with hashed run/trace keys. The worker
retries the HTTP *request* until success or the 24-hour SLA expires
(`sla_expired`). Request rows store ids/hashes only.

## Dedicated reaper (not budget true-up)

| Item | Default | Active/retryable |
| --- | --- | --- |
| Completed-run idempotency key | NULL after 7 days | `pending` / `running` keys never reaped |
| Completed `run_events` | Delete after 30 days | Events on active runs kept |

`app.reap_query_run_retention` never calls `app.true_up_query_reservation`.
After the plaintext key is NULLed, `app.runs.idempotency_key_hash` keeps
one-paid-run uniqueness for the same creator, conversation, and client
key. Conversation deletion purges keys and events immediately and does
not wait for 7/30-day windows.

Worker job kinds `query_memory_reaper` and `langsmith_trace_deletion` are
enqueued by `app.enqueue_query_maintenance_jobs`.

## Feedback tags

Thumbs feedback requires exactly one unmerged tag:

`chunk/cleaning loss`, `profile field wrong`, `candidate miss`,
`wrong rerank`, `bad refusal/overconfident answer`,
`missed relationship`, `wrong route`, `wrong calculation`,
`bad citation`, `insufficient graph`.

## Curation schedule

Owner/admin/SME curation is weekly during the pilot and the first eight
production weeks, then monthly after failure/alias volume stabilizes.
Approved aliases promote promptly. Confirmed failures become a versioned
post-launch regression set that stays disjoint from the immutable launch
holdout.

## Verification

```text
uv run python -m pytest tests/unit/test_conversation_deletion.py tests/contract/test_query_memory_reaper.py tests/contract/test_query_memory_summary.py tests/contract/test_query_memory_deletion.py tests/contract/test_query_memory_langsmith.py tests/unit/test_prompt_registry.py -q
```

## Failure modes

- Foreign DELETE or GET after tombstone → 404, no existence leak.
- Store write with source keys → `StorePayloadError`.
- Summary when remaining calls or USD cannot cover the cap →
  `summary_deferred`, no ceiling enlargement.
- Reaper on `pending`/`running` → zero keys nulled for those rows.
- LangSmith HTTP failure → retry; after 24h the row is `sla_expired`
  without claiming cloud deletion.
