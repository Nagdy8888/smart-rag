---
title: Foundation configuration contract
owner: engineering-lead
status: verified
last-reviewed: 2026-08-16
audience: developers, operators
---

# Foundation configuration contract

Python deployables read process environment only through
`smart_rag_core.settings`. Importing an entrypoint does not instantiate settings
or provider/database clients. FastAPI validates backend settings during
lifespan startup; console entrypoints validate before starting their process.
Validation errors list field paths and categories but omit source values.

## Shared deployable variables

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `APP_ENV` | `local`, `test`, `staging`, or `production`; `local` | public | Deployment label added to every structured log |
| `MOCK_MODEL_MODE` | boolean; `true` | public | Secure default; selects frozen fixtures and denies DNS access to `api.openai.com` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`; `INFO` | public | Root JSON log threshold |
| `OPENAI_API_KEY` | optional secret in mock mode | secret | Required when `MOCK_MODEL_MODE=false`; never logged or represented in plaintext |
| `LANGSMITH_TRACING` | boolean; `false` | public | Off by default. When true, every gateway model/embedding call emits a redacted LangSmith span. See [LANGSMITH_TRACING.md](./LANGSMITH_TRACING.md) |
| `LANGSMITH_API_KEY` | optional secret | secret | Required when `LANGSMITH_TRACING=true`; never logged or represented in plaintext |
| `LANGSMITH_PROJECT` | safe identifier; `smart-rag` | public | LangSmith project that receives redacted traces |
| `LANGSMITH_ENDPOINT` | optional HTTP URL | internal | Override for a non-default LangSmith API; unset uses the hosted default |
| `MOCK_MODEL_FIXTURE_ID` | safe identifier; `phase-1-foundation-v1` | internal | Included in fixture provenance; does not imply retrieval |
| `MODEL_INPUT_MAX_CHARS` | integer 1–65,536; 16,384 | public | Deployable gateway input bound |
| `VALKEY_LIMITS_URL` | optional URL | secret | Rate-limit Valkey. Packet 5 connects per command at request time, never at import. Unset falls back to Postgres for mutations |
| `VALKEY_CACHE_URL` | optional URL | secret | Cache Valkey. Never authority; retrieval hits recheck Postgres |
| `PARADEDB_URL` | optional URL | secret | Worker/API ParadeDB DSN. Packet 8 host pytest uses `docker-compose.packet8.yml` loopback `:54329` |
| `CRAWL_PROXY_URL` | optional HTTP URL | internal | Private deny-by-default proxy endpoint. Packet 8 overlay publishes `http://127.0.0.1:18080` |
| `CLAMAV_HOST` / `CLAMAV_PORT` | hostname / Packet 8 overlay `13310` | internal | Worker uses Compose DNS `clamav:3310`. Packet 8 overlay publishes host `13310` |
| `SMART_RAG_REQUIRE_CLAMAV` | `1` fails closed | public | Contract tests fail instead of skip when ClamAV is down |
| `SMART_RAG_REQUIRE_CRAWL_PROXY` | `1` fails closed | public | Live proxy overlay tests fail instead of skip |
| `SMART_RAG_REQUIRE_JOB_INTEGRATION` | `1` fails closed | public | Postgres job/checkpointer tests fail instead of skip |
| `SMART_RAG_HOLDOUT_ACCESS` | boolean; `false` | public | Default denies sealed holdout labels. Packet 8 freeze refuses to run when true. Enable only for an independently SME-sealed holdout or dataset seal verify |
| `SMART_RAG_HOLDOUT_ACCESS_PURPOSE` | `packet8_immutable_holdout` or `dataset_seal_verify` | internal | Required when holdout access is enabled |
| `SMART_RAG_HOLDOUT_ACCESS_ACTOR` | safe identifier | internal | Auditable actor required when holdout access is enabled |
| `ADMIN_ALERT_SMTP_HOST` | optional hostname; empty skips SMTP | internal | Local Inbucket/Mailpit host. Unset skips mail; set `127.0.0.1` for Packet 8 proof |
| `ADMIN_ALERT_SMTP_PORT` | integer; `54325` | public | Exposed local SMTP port from `supabase/config.toml` `local_smtp.smtp_port` |
| `ADMIN_ALERT_SMTP_FROM` | email; `alerts@localhost` | public | Envelope from for metadata-only admin alerts |
| `ADMIN_ALERT_SMTP_TO` | email; `owner@localhost` | public | Owner/admin mailbox captured by Inbucket |

## Phase 5 LightRAG settings

Packet 1 qualification still applies `POSTGRES_*` through tests only. Packet 2
adds deployable DSNs. Runtime never sets `POSTGRES_WORKSPACE`. Passwords are
never logged. See [ADAPTER_LIFECYCLE.md](../graph/ADAPTER_LIFECYCLE.md) and
[ADR-lightrag-runtime-attach-without-ddl.md](../adr/ADR-lightrag-runtime-attach-without-ddl.md).

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `LIGHTRAG_DB_URL` | optional secret URL | secret | Backend and Worker only. Session/direct Postgres for runtime attach as `app_lightrag` via `SET ROLE`. Unset keeps the adapter unconfigured. Never schema-admin. Cap 4. |
| `LIGHTRAG_SCHEMA_ADMIN_DSN` | required for ops bootstrap | secret | `LightRagSchemaAdminSettings` only. Forbidden on Shared/Backend/Worker/Agent. Used by `scripts/ops/bootstrap_lightrag_schema.py`. |

Qualification-only (tests still apply these; production modules set them from the typed DSN):

| Variable | Qualification value | Contract |
| --- | --- | --- |
| `POSTGRES_HOST` / `PORT` / `USER` / `PASSWORD` / `DATABASE` | Parsed from the typed DSN | Never logged. |
| `POSTGRES_MAX_CONNECTIONS` | `2` in qualification; `4` runtime cap | Process-wide `ClientManager` pool. |
| `POSTGRES_CONNECTION_RETRIES` | `0` | Vendor default 10 is unbounded; application owns retry. |
| `POSTGRES_SERVER_SETTINGS` | `search_path=lightrag,extensions,public` | Private schema first; pgvector lives in `extensions`. |
| (harness, not env) | `install_pgvector_codec_schema_fallback` | LightRAG calls `register_vector` with `schema='public'`; local Supabase type is `extensions.vector`. |
| (harness, not env) | `cosine_better_than_threshold=-1.0` | Qualification only. Do not copy into production Graph settings (`0.2` vendor default). |
| `POSTGRES_WORKSPACE` | unset except the override test | When set, runtime attach fails closed. |
| `WORKSPACE` | unset | LightRAG constructor default also reads this name. |

Incompatible embedding model/dimension instances must run in isolated
processes. This process pins `text-embedding-3-large` at 1024.

See [LIGHTRAG_CONTRACT.md](../graph/LIGHTRAG_CONTRACT.md).

## Backend-only variables

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `API_BIND_HOST` | non-empty string; `0.0.0.0` | public | Uvicorn bind address used only by the console entrypoint |
| `API_BIND_PORT` | integer 1–65,535; `8000` | public | Uvicorn container port |
| `JWKS_CACHE_SECONDS` | integer 1–600; `600` | public | JWKS cache TTL |
| `SUPABASE_DB_URL` | optional secret URL | secret | Server-side profile reads as `app_api` |
| `LIGHTRAG_DB_URL` | optional secret URL | secret | Runtime LightRAG attach. Unset = unconfigured. Never schema-admin. |
| `CORS_ALLOW_ORIGINS` | comma-separated exact origins; `http://127.0.0.1:3000,http://localhost:3000` | public | Wildcards forbidden. Never pair `*` with credentials |
| `API_VERSION` | `major.minor.patch`; `0.1.0` | public | Published by `GET /api/meta` |
| `SSE_SCHEMA_VERSION` | safe token; `1` | public | Published by `GET /api/meta` and the first SSE `schema` event |
| `MIN_CLIENT_VERSION` | `major.minor.patch`; `0.1.0` | public | Clients send `X-Client-Version` on new paid POST. Missing/below → 426 `client_version_unsupported` before admit. Resume GET does not require the header |
| `RETRIEVAL_CACHE_RESULT_TTL_SECONDS` | 1–300; `30` | public | ID/rank cache TTL |
| `RETRIEVAL_CACHE_PROFILE_TTL_SECONDS` | 1–3600; `300` | public | Profile/embedding cache TTL |
| `REQUEST_MAX_BODY_BYTES` | 1024–16_777_216; `1048576` | public | JSON/body cap; oversized → 413 |
| `VALKEY_TIMEOUT_SECONDS` | 0.05–2.0; `0.2` | public | Valkey connect/command timeout |
| `RATE_LIMIT_RETRY_AFTER_SECONDS` | 1–3600; `60` | public | `Retry-After` on limiter 429/503 |

`X-Client-Version` is a request header, not an environment variable. New paid
`POST /conversations/{conversation_id}/messages` must send a semver-like value
greater than or equal to `MIN_CLIENT_VERSION`. See [SSE.md](../api/SSE.md).

Phase 6 packet 1 query admission still uses
`QUERY_ADMISSION_RATE_MAX_ATTEMPTS=20` / 60s as engineering defaults. Packet 5
classifies that bucket as `COST_MUTATION` (Valkey then Postgres, never
fail-open).

## Worker-only variables

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `WORKER_ONCE` | boolean; `false` | public | Exit after one poll/claim cycle |
| `SUPABASE_DB_URL` | optional secret URL | secret | Worker-role session/direct Postgres DSN for claim/heartbeat |
| `WORKER_INSTANCE_ID` | string; `worker-local` | internal | Lease owner identifier for this process |
| `JOB_LEASE_SECONDS` | integer 30–3600; `300` | public | Claim and heartbeat lease duration |
| `JOB_HEARTBEAT_INTERVAL_SECONDS` | integer 10–900; `60` | public | Heartbeat cadence while a job is leased |
| `JOB_POLL_INTERVAL_SECONDS` | integer 1–60; `5` | public | Idle delay between queue polls |
| `WORKER_CONCURRENCY` | integer 1–8; `2` | public | Maximum concurrently processed ingestion jobs |
| `LANGGRAPH_CHECKPOINT_URL` | optional secret URL | secret | Checkpointer DSN; defaults to `SUPABASE_DB_URL`. Role `app_checkpointer`, schema `langgraph`. Runtime never auto-migrates. |
| `LIGHTRAG_DB_URL` | optional secret URL | secret | Runtime LightRAG attach. Unset = unconfigured. Never schema-admin. Cap 4. |

Agent settings currently add only a stable, non-environment service name.
Queue and retrieval settings remain owned by later phases. Graph runtime DSN
is Packet 2 above. Packet 3 reuses `JOB_LEASE_SECONDS` for graph job and
writer leases. Graph Ready remains Packet 4.

Phase 6 packet 1 query admission adds **no new environment variables** beyond
the packet 5 backend table above. FastAPI rate limits use
`QUERY_ADMISSION_RATE_MAX_ATTEMPTS=20` / 60s window classified as
`COST_MUTATION`.

## Managed proof-operation variables

The destructive JWKS rollover script loads its values through
`JwksRolloverSettings`, not direct process-environment reads:

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `SUPABASE_ACCESS_TOKEN` | required secret | secret | Short-lived Management API token |
| `SUPABASE_PROJECT_REF` | required safe identifier | internal | Explicit managed project target |
| `SUPABASE_MANAGED_URL` | required HTTP URL | internal | Managed Auth/JWKS origin |
| `SUPABASE_ANON_KEY` | required key | secret | Publishable Auth key redacted from settings representations |

Protected LightRAG bootstrap loads `LIGHTRAG_SCHEMA_ADMIN_DSN` through
`LightRagSchemaAdminSettings` only. See the Phase 5 LightRAG settings table.

## Local Compose-only variables

These placeholders are consumed by Docker Compose rather than Python settings:

- `API_HOST_PORT` and `FRONTEND_HOST_PORT` publish the two documented developer
  endpoints.
- `PARADEDB_DB`, `PARADEDB_BOOTSTRAP_USER`,
  `PARADEDB_BOOTSTRAP_PASSWORD`, `PARADEDB_WRITER_USER`,
  `PARADEDB_WRITER_PASSWORD`, `PARADEDB_READER_USER`, and
  `PARADEDB_READER_PASSWORD` configure private local ParadeDB roles.
- `VALKEY_LIMITS_PASSWORD` and `VALKEY_CACHE_PASSWORD` are distinct private
  local credentials.

`SUPABASE_URL` and `SUPABASE_ANON_KEY` remain commented Compose placeholders.
`LANGSMITH_API_KEY` is a typed SharedSettings secret, still optional while
tracing is off. Backend Packet 4+ reads `SUPABASE_URL` /
JWKS settings through `BackendSettings`. Privileged secrets
`SUPABASE_AUTH_ADMIN_SECRET` and `SUPABASE_STORAGE_ADMIN_SECRET` are never
declared on `SharedSettings`, `BackendSettings`, `WorkerSettings`, or
`AgentSettings`. Auth Admin loads through `smart_rag_api.auth_admin`. Storage
Admin loads through `smart_rag_api.storage_admin` (API) and
`smart_rag_worker.privileged_storage` (worker).

## Failure and security behavior

- Real-model mode without `OPENAI_API_KEY` fails startup.
- Tracing enabled without `LANGSMITH_API_KEY` fails startup.
- Invalid values fail startup with a sanitized `SettingsValidationError`.
- Mock responses are deterministic, bounded, provenance-marked, and explicitly
  state that no retrieval or provider work occurred.
- The mock lifecycle guard restores the original DNS resolver at shutdown.
- Logs whitelist deployment/correlation metadata, redact common credential
  forms, truncate long messages, and omit exception text.

## Verification

```powershell
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier contract
uv run python scripts/check.py --tier types
```

See [Phase 1 foundation evidence](./phase-01-foundation-evidence.md) for recorded
exit codes.
