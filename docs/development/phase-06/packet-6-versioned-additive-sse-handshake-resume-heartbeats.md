# Packet 6 — versioned additive SSE, handshake, resume, heartbeats

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Quoted requirement

> Implement versioned additive API/SSE contracts, compatibility handshake,
> resumable fetch SSE with persisted sequence IDs, heartbeats, cancellation,
> reconnect, sanitized errors, and deadline/partial events.

## Acceptance checks restated

- Incompatible clients fail with HTTP 426 `client_version_unsupported`
  **before** `admit_query_run_for_caller`. No reservation, no graph start.
  Resume GET of an already-admitted run requires Bearer + ownership only.
- Bearer POST fetch SSE (`Accept: text/event-stream`) admits then streams.
  JSON Accept stays HTTP 202 `{run_id, stream_path}` with
  `stream_path=/runs/{run_id}/events`. Duplicate idempotency keys reuse one
  run and do not start the executor twice.
- Every event (including heartbeat) is persisted with a monotonic run-local
  sequence **before** flush. `GET /runs/{run_id}/events?after=` and
  `Last-Event-ID` replay `sequence > after`. Foreign / missing / tombstoned
  conversations are 404.
- Reconnect never restarts paid execution. Process-local registry starts
  LangGraph (or the test fixture) at most once per `run_id`. A pending run
  with no live executor after process restart replays a sanitized
  `worker_unavailable` error.
- Heartbeats every **15 seconds** while a stream is open and the run is
  non-terminal. Cancel persists `cancelled` and stops the live generator.
- Local Caddy contract file uses `flush_interval -1` and **90s** timeouts.
  Docs name CloudFront `OriginReadTimeout` / `OriginKeepaliveTimeout` = 90s
  as Phase 10 IaC. This packet does not provision AWS or claim CDN proof.

## Event catalog (allow-list; extra=forbid)

`schema`, `status`, `heartbeat`, `route_correction`, `limitation`,
`deadline`, `partial`, `cache`, `coverage`, `optional_tool_disclosure`,
`citation_preview` (IDs/ranks only), `token_delta`, `usage`, `completed`,
`cancelled`, `error` (generic `{code}`; no traceback/secrets/HTML/passage).

Exactly one terminal among `completed` | `cancelled` | `error` | `partial`.
Deadline exhaustion emits `deadline` then `partial`. Clients log and ignore
unknown additive types.

Wire format (FastAPI 0.141 has no `EventSourceResponse`):

```text
id: {sequence}
event: {allowlisted_type}
data: {json}
```

SSE headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
`Connection: keep-alive`, `X-Accel-Buffering: no`. Packet 5 security
middleware does not rewrite `text/event-stream` to JSON.

## Handshake versus reservation

| Case | Admit calls | Executor starts | HTTP |
| --- | --- | --- | --- |
| Missing `X-Client-Version` | 0 | 0 | 426 + published `min_client_version` / `sse_schema_version` |
| `X-Client-Version: 0.0.1` below min | 0 | 0 | 426 |
| Supported version + JSON Accept | 1 | 0 until GET resume | 202 |
| Supported version + EventSource Accept | 1 | 1 | 200 stream |
| Duplicate idempotency key | 2 (reconnect) | 1 | existing run |
| GET resume without client version | n/a | at most one | 200 replay |

Proven by `tests/unit/test_sse_protocol.py` and
`tests/contract/test_sse_resume.py`.

## Sequence / replay

- Memory and Postgres `app.append_run_event` allocate
  `COALESCE(MAX(sequence),0)+1` under a run lock after ownership and
  undeleted-conversation checks.
- Postgres contract: sequences `(1, 2, 3)`, `after=1` returns `(2, 3)`,
  foreign list and tombstoned `conversations.deleted_at` raise `not_found`,
  `app_api` cannot `INSERT` into `app.run_events` directly.
- Unique partial index enforces one terminal event per run.

## Heartbeat / event-loop (five held streams)

Five concurrent fixture SSE GETs were held while lag was sampled for ≥16 s
(`httpx.ASGITransport` + `asyncio.gather`). Production interval constant
`HEARTBEAT_INTERVAL_SECONDS == 15`. Cadence was measured from **persisted**
heartbeat rows (same append path as the socket) because ASGITransport
delivers the EventSource body when the generator completes.

Gates asserted in `tests/contract/test_sse_heartbeat.py`:

- p95 event-loop lag `< 50 ms` (`sample_event_loop_lag`)
- first persisted heartbeat jitter `< 2 s` around 15 s
- zero missed 15-second heartbeats (every held run persisted ≥1 heartbeat)

No OpenAI. Live Composite LLM streaming remains packet 8.

## Timeout contract (local files only)

| Input | Value | Proof |
| --- | --- | --- |
| Caddy `read_timeout` / `write_timeout` / upstream | 90s | `infra/caddy/Caddyfile` |
| Caddy buffering | `flush_interval -1` | same file |
| CloudFront `OriginReadTimeout` | 90s | `docs/deployment/STREAMING_TIMEOUTS.md` (Phase 10 IaC) |
| CloudFront `OriginKeepaliveTimeout` | 90s | same doc |
| Composite deadline | 50s | margin under 90s |

`tests/contract/test_streaming_timeout_contract.py` fails if any parsed
value ≠ 90. Caddy is **not** deployed. CloudFront is **not** provisioned.

## OpenAPI

Additive `GET /runs/{run_id}/events` (path param remains `run_id`).
POST `/conversations/{conversation_id}/messages` documents JSON 202 and
`text/event-stream` 200 plus 426 handshake. Snapshot
`docs/api/openapi.foundation.json` regenerated UTF-8.
`scripts/ci/check_openapi.py` allowlists `/runs/{run_id}/events`.

## Commands and exit codes

| Command | Exit |
| --- | --- |
| `uv run ruff format` (packet 6 Python) | 0 |
| `uv run ruff check` (packet 6 Python) | 0 |
| `uv run python -m pyright` (packet 6 Python) | 0 |
| `uv run python scripts/ci/check_migrations.py` | 0 (50 reviewed files) |
| `uv run python scripts/ci/check_openapi.py` | 0 (snapshot matches after UTF-8 regenerate) |
| `uv run python -m pytest tests/unit/test_sse_protocol.py tests/contract/test_sse_resume.py tests/contract/test_sse_heartbeat.py tests/contract/test_streaming_timeout_contract.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py tests/unit/test_fastapi_security.py tests/contract/test_query_admission_api.py -q` | 0 (54 passed) |

`npx supabase migration up --db-url postgresql://postgres:postgres@127.0.0.1:54322/postgres`
applied `20260816200000_query_run_events_v1.sql` (no `db reset`). Backend
import still constructs no sockets/OpenAI (`test_package_imports`).

## Deviations

- FastAPI **0.141.1** has no `fastapi.sse.EventSourceResponse`. SSE uses
  Starlette `StreamingResponse` and manual framing (planned pin; no bump).
- JSON 202 is returned via `JSONResponse(status_code=202)` because
  `response_model=None` would default POST to 200 when the EventSource
  200 is also declared.
- Five-stream heartbeat jitter is measured from persisted rows, not
  `aiter_text` timestamps. Documented above.
- Production executor is `LangGraphQueryRunExecutor` (`graph.astream`
  once). HTTP tests inject `FixtureQueryRunExecutor`. Both persist through
  the same `RunEventStore.append` path.

## Rollback

- Drop/leave unused `app.run_events` / `app.append_run_event` /
  `app.list_run_events_after` via a later expand/contract migration
  (do not `DROP TABLE` in this packet).
- Revert `docs/api/openapi.foundation.json` and the FastAPI SSE routes.
- Clients without `X-Client-Version` would again reach admit; do not ship
  that rollback without a replacement handshake.

## Phase 10 blockers

- CloudFront/WAF/Caddy **IaC** asserting 90s `OriginReadTimeout` and
  `OriginKeepaliveTimeout` (this packet only has local contract files).
- Real staging 50-second Composite stream through managed CDN (no buffering,
  no premature origin close).
- Independent Vercel/API deploy skew and origin-restriction checks.
- Do not treat `infra/caddy/Caddyfile` as proof that Caddy is deployed.

## Packet 7 handoff

- Completed idempotency keys default to **seven days**; completed events
  to **30 days** through a dedicated reaper. Packet 7 implements that reaper
  and immediate conversation deletion (HTTP 204).
- Do **not** implement packet 8 UI in packet 6. Do **not** mark Phase 6
  complete.
