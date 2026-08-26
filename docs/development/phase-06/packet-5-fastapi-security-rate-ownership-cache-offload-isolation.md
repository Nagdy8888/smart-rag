# Packet 5 — FastAPI security, rate ownership, cache, offload, isolation

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Quoted requirement

> Implement thin FastAPI routers/services, Supabase-Auth/FastAPI rate
> ownership, authorization-safe retrieval caching, endpoint-specific
> authorization, CPU offload, and prompt/data isolation.

## Acceptance checks restated

- Every listed endpoint has explicit role/ownership/current-version/
  deletion/ACL behavior; routers stay thin (`Depends` → service →
  factory-injected core/agent). No repository imports in packet 5 routers.
- Provider-owned Auth and FastAPI-owned rate controls are separately
  documented; FastAPI never claims to throttle browser-direct Auth
  (`local_auth_throttling_proven=False`).
- Valkey loss: AUTH_ADJACENT / COST_MUTATION / PRE_AUTH_IP use Valkey then
  Postgres and 503 + Retry-After if both fail. LOW_RISK_READ may use an
  emergency in-process limiter with `rate_limit_degraded`.
- Separate Valkey instances: limits `64mb` / `mem_limit 128m` /
  `noeviction`; cache `256mb` / `320m` / `allkeys-lru`; `requirepass`;
  private network; no host ports. 64mb is 50% of 128m (≤ 70%).
- Retrieval cache stores IDs/ranks only (TTL 30s / 300s). Every hit
  rechecks; ACL/delete/version mismatch and forbidden snippet/text/passage
  fields drop the entry. Events: `cache_hit`, `cache_miss`,
  `cache_invalidated`, `cache_recheck_failed`.
- CPU slices over 10 ms offload through a bounded cancellable process
  pool; blocking I/O uses a thread pool. Five live Composite heartbeat
  proofs remain packets 6 and 8.
- Extra JSON fields and untrusted HTML fail closed (422 / escaped JSON,
  never `text/html`). Local audit export detects mutation, gap, fork,
  signing failure, and passage-like keys without storing full source text.

## Inspected schema / APIs

| Item | Found |
| --- | --- |
| Latest additive migration | `20260816190000_fastapi_security_rpcs_v1.sql` |
| Conversation delete RPC | Not implemented; DELETE HTTP is 501 `conversation_deletion_not_implemented` |
| Auto admit envelope | HTTP maps Auto chat to `Phase6RouteFamily.COMPOSITE` |
| Stream path | `{run_id, stream_path}` with `/runs/{run_id}/events`; no EventSource body |
| OpenAPI snapshot | `docs/api/openapi.foundation.json` regenerated UTF-8 |
| Valkey Compose | `docker-compose.yml` `valkey-limits` / `valkey-cache` as above |
| CORS default | `http://127.0.0.1:3000,http://localhost:3000`; `*` rejected |

## Endpoint authorization matrix

| Method | Path | Authorization | Notes |
| --- | --- | --- | --- |
| GET | `/health/live` | public | Process up |
| GET | `/health/ready` | public | Dependency-aware; `query_ready` is false in mock/unconfigured |
| GET | `/api/meta` | public | Publishes `api_version`, `sse_schema_version`, `min_client_version` |
| GET | `/me` | authenticated | Server-derived role |
| POST | `/admin/invitations` | owner/admin | AUTH_ADJACENT |
| POST | `/invitations/accept` | authenticated | Email from token, not body |
| POST | `/admin/users/{user_id}/offboard` | owner/admin AAL2 | AUTH_ADJACENT |
| GET | `/documents` | authenticated | ACL list |
| GET | `/documents/{document_id}` | authenticated | 404 if missing/unauthorized |
| POST | `/documents/uploads` | member+ upload | COST_MUTATION; local `signed_url=null` |
| POST | `/documents/uploads/finalize` | member+ upload | COST_MUTATION |
| POST/GET | `/conversations` | authenticated | Creator insert / list |
| GET | `/conversations/{conversation_id}` | creator or owner/admin | 404 otherwise |
| DELETE | `/conversations/{conversation_id}` | authenticated | **501** packet 7 |
| POST | `/conversations/{conversation_id}/messages` | creator | Auto → COMPOSITE; `{run_id, stream_path}` |
| GET | `/runs/{run_id}` | creator only | IDOR → 404 |
| POST | `/runs/{run_id}/cancel` | creator | Not SSE cancel transport |
| GET | `/runs/{run_id}/citations` | creator | IDs/provenance; no passage |
| POST | `/runs/{run_id}/feedback` | creator | thumbs 1 or 5 |
| GET | `/graph/entities/search` | authenticated | Cheap SQL; 3s timeout |
| GET | `/tables` | authenticated | Current-version manifests; no paths |
| POST | `/tables/analyze` | authenticated | `TableQueryPlan` extra=forbid |
| GET | `/tools` | authenticated | In-code registry + live role; Postgres not required |
| POST | `/admin/tools` | owner/admin | Allow-listed keys only |
| POST | `/admin/tools/{tool_key}/enable` | owner/admin | Allow-list recheck |
| POST | `/admin/tools/{tool_key}/permissions` | owner/admin | Executor still rechecks live role |
| GET | `/usage/me` | authenticated | Caller totals |
| GET | `/usage/company` | owner/admin | Members/viewers 403 |

## Valkey / cache / offload proof

| Check | Result |
| --- | --- |
| Limits `maxmemory` / `mem_limit` / policy | `64mb` / `128m` / `noeviction` in `docker-compose.yml` |
| Cache `maxmemory` / `mem_limit` / policy | `256mb` / `320m` / `allkeys-lru` |
| Host ports / network | none / `private`; `requirepass`; named ACL users Phase 10 |
| Key prefixes | `limits:` and `cache:` in `smart_rag_core.runtime.valkey` |
| Cache TTLs | result 30s, profile 300s |
| Cache recheck | `test_retrieval_cache.py`: drop/flip/forbidden payload → miss; no stale IDs |
| Import-time sockets | `test_package_imports.py` still denies socket/OpenAI construction |
| Offload / cancel | `test_cpu_slice_budget_and_offload_cancel`: 10 ms budget, thread/process offload, `OffloadCancelledError` |
| Event-loop lag | `sample_event_loop_lag` unit-sampled; five live Composite runs are packet 8 |
| Lifespan OffloadExecutor | **Not** started in FastAPI lifespan (Windows TestClient/process-pool hang) |

## Rate ownership

| Check | Result |
| --- | --- |
| Browser-direct Auth | FastAPI does not claim it; flag false |
| Dual Valkey+Postgres outage on mutations | `AuthRateLimitUnavailableError` / HTTP 503 Retry-After |
| Unconfigured (both URLs unset) | Pre-auth middleware skips; not treated as dual outage |
| LOW_RISK_READ Valkey loss | Emergency limiter + `rate_limit_degraded` |
| Reserve-once vs limiter | Packet 1 admission reservations stay separate from FastAPI buckets |

## Isolation / audit

| Check | Result |
| --- | --- |
| Conversation title HTML | Escaped in JSON; content-type `application/json` |
| Extra JSON fields | 422 `validation_failed` |
| Oversized body | 413 `payload_too_large` |
| CORS | Exact origin reflected; evil origin omitted; `*` settings fail |
| Viewer tools | `admin_user_invite` omitted; core forbidden keys omitted |
| Foreign run fetch | 404 `not_found` |
| Local HMAC export | mutation / gap / fork / empty / passage key / empty secret fail closed |

## Commands and results

| Command | Exit |
| --- | --- |
| `uv run ruff format` on packet 5 Python paths | 0 |
| `uv run ruff check` on packet 5 Python paths | 0 |
| `uv run python -m pyright` on packet 5 changed Python paths | 0 errors |
| `uv run python scripts/ci/check_migrations.py` | 0 (49 reviewed files) |
| `uv run python scripts/ci/check_openapi.py` | 1 then 0 (snapshot rewritten UTF-8, then matches) |
| `uv run python -m pytest tests/unit/test_fastapi_security.py tests/contract/test_query_admission_api.py tests/contract/test_retrieval_cache.py tests/unit/test_package_imports.py tests/contract/test_import_boundaries.py tests/unit/test_backend_middleware.py tests/contract/test_auth_rate_limits.py tests/unit/test_settings.py` | 0; **57 passed**, 7 warnings, 0 failed |

## Deviations

- FastAPI lifespan does not construct `OffloadExecutor` because Windows
  `TestClient` plus a process pool hung import/readiness tests. Offload
  and cancellation are proven in unit tests; query nodes remain responsible
  for calling the executor when a slice exceeds 10 ms.
- Named Valkey ACL users and Secrets Manager rotation are Phase 10. Local
  Compose uses `requirepass` on the private network (ADR-private-service-tls
  omits TLS).
- Pre-auth IP limits skip when **neither** Valkey nor Postgres is configured
  so unconfigured processes are not treated as a dual outage.
- Local document upload `signed_url` is null (CloudFront is Phase 10).
- Conversation DELETE is 501 until packet 7.
- Five simultaneous Composite p95 lag / heartbeat proofs are packets 6 and 8.

## Rollback

Forward-fix: stop including the new routers and keep `/health` plus prior
ingestion/glossary/graph-inspect routes. Do not DROP the additive
`20260816190000` RPCs in the same release. Restore
`docs/api/openapi.foundation.json` from the prior commit if reverting the
snapshot.

## Phase 9 / 10 blockers

- Phase 9: reservation-lock wait at max concurrency (provisional p95 below 50 ms).
- Phase 10: KMS key unavailable to database roles; 15-minute chain-head
  anchors; signed daily batches to S3 Object Lock; named Valkey ACL +
  Secrets Manager; hosted Auth throttle proof; CloudFront signed URLs /
  WAF / origin restriction.

## Packet 6 handoff

- Implement `GET /runs/{run_id}/events` EventSource transport, SSE schema,
  15s heartbeat, resume, and cancel **without** inventing event names in
  packet 5.
- Enforce `min_client_version` / `sse_schema_version` handshake before paid
  work. Packet 5 only publishes those fields on `/api/meta`.
- Keep Auto admit on the Composite envelope and `stream_path`
  `/runs/{run_id}/events`.
- Do **not** mark Phase 6 complete. Do **not** check the wrapper checkbox.

## Unverified (packet 5)

- Live Postgres round-trips for the new conversation/run/document/table/
  tool-seed RPCs (HTTP tests inject services or unused DSNs).
- Live Valkey kill / restart / OOM / ACL recovery against Compose.
- Five live Composite runs (heartbeat jitter, missed 15s heartbeat).
  Packet 6 proved five **fixture** streams; live Composite LLM remains
  packet 8.
- Hosted Auth throttling (carried).
- QT-EVAL-009 and Combined p95 latency (carried).
- Phase 9 lock-wait measurement and Phase 10 AWS proof.
