---
title: SSE protocol and resume
owner: engineering-lead
status: draft
last-reviewed: 2026-08-26
audience: engineering, frontend
---

# Server-Sent Events

Bearer fetch SSE for Auto chat. FastAPI 0.141 has no `EventSourceResponse`;
frames are written with `StreamingResponse` and media type `text/event-stream`.

Related: [FASTAPI_SECURITY.md](./FASTAPI_SECURITY.md) ·
[STREAMING_TIMEOUTS.md](../deployment/STREAMING_TIMEOUTS.md) ·
[ADR-api-sse-compatibility](../adr/ADR-api-sse-compatibility.md) ·
[openapi.foundation.json](./openapi.foundation.json)

## Handshake then admit

```mermaid
sequenceDiagram
  participant Client
  participant API as FastAPI
  participant Admit as admit_query_run
  participant Events as run_events
  participant Graph as QueryRunExecutor
  Client->>API: "POST /conversations/{conversation_id}/messages"
  Note over Client,API: "X-Client-Version and Bearer"
  alt missing or below min_client_version
    API-->>Client: "426 client_version_unsupported"
  else handshake ok
    API->>Admit: "reserve Composite envelope"
    Admit-->>API: "run_id"
    API->>Events: "append schema then flush"
    API->>Graph: "start once pending to running"
    loop every 15s while non-terminal
      API->>Events: "append heartbeat then flush"
    end
    Client->>API: "GET /runs/{run_id}/events?after={sequence}"
    API->>Events: "list_run_events_after"
    API-->>Client: "replay sequence greater than after"
    Client->>API: "POST /runs/{run_id}/cancel"
    API->>Events: "append cancelled"
    API->>Graph: "cancel live executor"
  end
```

`GET /runs/{run_id}/events` requires Bearer and ownership. It does **not**
repeat the version handshake. Tombstoned `conversations.deleted_at` denies
resume with 404. Reconnect never starts a second paid graph.

## Transport

- `POST /conversations/{conversation_id}/messages` with `Accept: text/event-stream`
  admits (after handshake) then streams. JSON Accept keeps HTTP 202
  `{run_id, stream_path}` where `stream_path=/runs/{run_id}/events`.
- Duplicate idempotency keys return the existing run stream.
- `GET /runs/{run_id}/events?after={sequence}` also honors `Last-Event-ID`.
  Replay is strictly `sequence > after`. `after=0` or omitted means from start.
- Headers on SSE responses: `Content-Type: text/event-stream`,
  `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`.

## Event catalog

Clients ignore unknown additive types (log and continue). Payloads use
`extra=forbid`. Citation preview is IDs/ranks only. Errors never include
tracebacks, secrets, source HTML, or passages.

| Type | Role |
| --- | --- |
| `schema` | First event on a new stream. Carries `sse_schema_version`. |
| `status` | Stage/status. |
| `heartbeat` | Every 15 seconds, persisted, while the run is non-terminal. |
| `route_correction` | Single-correction diagnostic. |
| `limitation` | Named limitation code. |
| `deadline` | Deadline exhaustion notice. |
| `partial` | Verified partial terminal (after `deadline` when exhausted). |
| `cache` | Cache diagnostic. |
| `coverage` | Coverage score without passage text. |
| `optional_tool_disclosure` | Selected optional tool keys. |
| `citation_preview` | Citation IDs and ranks. No passage text. |
| `answer_origin` | Additive origin (`origin` only). Emitted before `token_delta` on new answers. Schema major version stays `1`. Historical/null payloads omit the event. |
| `token_delta` | Generated token delta. Never retrieved source. |
| `usage` | Accumulated provider prompt and completion tokens for the run. Emitted after verify, before the terminal. Counts are 0 when no model ran. No prompts. |
| `completed` | Success terminal. |
| `cancelled` | Cancel terminal. |
| `error` | Sanitized `{code}`. |

Ask never infers origin from `route_family`. Citation chips render only
for `company_documents` or a missing legacy origin. General, user-text,
deterministic, ambiguous, and unknown origins hide chips.

Exactly one terminal among `completed`, `cancelled`, `error`, `partial`.
Conversation summary and assistant-message persist run only after that
terminal is yielded. Those writes must not emit a second `error`.

Live `LangGraphQueryRunExecutor` compiles **per execute** with
`build_query_graph_deps`: Hybrid (DSN-based, ParadeDB optional), counted
`model_gateway` (mock gateway is still a gateway), pinned `answer_v1` /
`verified_v1` bodies, optional process LightRAG adapter, structured-table
`structured_table_query`, per-run `app_api` connection, and per-run
`cancel_check`. Missing Hybrid or gateway fails closed. A failed per-run
`app_api` connect is `error.code=app_api_connection_unbound`; the executor
does not continue with `connection=None`. Concurrent Combined retrieves
serialize `query_budget` onto the shared LightRAG adapter. Studio's
module-level `graph` stays unbound.

## Sanitization and reconnect

- Exception messages are discarded. Retrieved source text is never stored
  or streamed. Payload keys `passage`, `snippet`, `html`, and traceback-like
  names are stripped or rejected in `app.append_run_event`.
- Disconnect without cancel keeps already-paid usage. Reconnect resumes
  from `after` and does not invoke LangGraph again when status is already
  running/completed/cancelled/partial or this process has no live executor.
  While status is `running`, a replica with an empty local registry
  **replays only** and must not persist `error` `{code: worker_unavailable}`
  (that unique terminal would block the owning replica from appending
  `completed`). `worker_unavailable` is only for a true orphan: `pending`
  with no startable input on this process.

## Persist offload and run-row locks

```mermaid
sequenceDiagram
  participant EventLoop as AsyncioLoop
  participant Worker as AppendThread
  participant Graph as GraphTxn
  participant Store as RunEvents
  EventLoop->>Worker: "to_thread append heartbeat"
  Graph->>Graph: "uncommitted llm_usage KEY SHARE"
  Worker->>Store: "append_run_event FOR UPDATE"
  alt lock held
    Store-->>Worker: "lock_timeout 2s"
    Worker-->>EventLoop: "log and skip heartbeat"
  else lock free
    Store-->>Worker: "sequenced event"
    Worker-->>EventLoop: "persist then continue"
  end
  EventLoop->>Graph: "astream yield then commit"
```

Heartbeat and executor appends run in `asyncio.to_thread` so a synchronous
Postgres wait cannot freeze the SSE event loop or LangGraph `astream`.
Sequence order is unchanged: each append is awaited before the next event.
Exactly one terminal remains required.

`PostgresRunEventStore` keeps autocommit off. After `SET ROLE app_api` each
transaction applies `SET LOCAL lock_timeout TO '2s'`. That matches the
intended `app_api` GUC. Hosted login-role sessions do not always inherit
role timeouts after `SET ROLE`, so the store must set the limit itself.

`app.append_run_event` takes `SELECT … FROM app.runs FOR UPDATE`. An
uncommitted `llm_usage` insert on the graph `app_api` connection holds
KEY SHARE on the same row until the executor commits after an `astream`
yield. A heartbeat that hits that lock must fail in two seconds, not sit
until the 120-second statement timeout. Heartbeat failures are logged and
skipped. Status and terminal append failures keep the previous None-return
path so the executor can persist a sanitized `error`. Logs include
`run_id`, `sse_event_type`, SQLSTATE or reason, and elapsed seconds.
They never include DSNs, JWTs, payload bodies, or exception text.

This is the c31e50dc stall class. Disabling LangSmith tracing is not the
fix. Authenticated live timing after this repair is still unverified.

## Retention (packet 7)

Completed idempotency keys default to seven days and completed events to
30 days through `app.reap_query_run_retention`. Conversation deletion
purges keys/events immediately. Tombstones deny resume. See
[MEMORY_DELETION.md](../agent/MEMORY_DELETION.md).
