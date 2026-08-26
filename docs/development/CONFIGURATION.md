---
title: Foundation configuration contract
owner: engineering-lead
status: verified
last-reviewed: 2026-08-26
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
| `APP_ENV` | `local`, `test`, `staging`, or `production`; `local` | public | Deployment label added to every structured log. `local` also enables the documented JWT `iss` hostname pair under backend `SUPABASE_URL` |
| `ALLOW_TEST_IDENTITY` | boolean; `false` | public | `X-Test-*` headers mint a caller only together with `APP_ENV=test`. Staging and production reject the flag at settings load |
| `MOCK_MODEL_MODE` | boolean; `true` | public | Secure default; selects frozen fixtures and denies DNS access to `api.openai.com`. Local live OpenAI is opt-in via gitignored env (`false` plus `OPENAI_API_KEY`). Real company content stays prohibited until the OpenAI org matrix is `verified` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`; `INFO` | public | Root JSON log threshold |
| `OPENAI_API_KEY` | optional secret in mock mode | secret | Required when `MOCK_MODEL_MODE=false`; never logged or represented in plaintext |
| `LANGSMITH_TRACING` | boolean; `false` | public | Off by default. When true, every gateway model/embedding call emits a redacted LangSmith span. Local Compose reads this from `.env.compose`, not leftover host pytest flags. See [LANGSMITH_TRACING.md](./LANGSMITH_TRACING.md) |
| `LANGSMITH_API_KEY` | optional secret | secret | Required when `LANGSMITH_TRACING=true`. Local LangGraph Studio UI also needs this key to attach at `smith.langchain.com/studio` even when tracing stays false. Never logged or represented in plaintext |
| `LANGSMITH_PROJECT` | safe identifier; `smart-rag` | public | LangSmith project that receives redacted traces. Open this exact project in the UI |
| `LANGSMITH_ENDPOINT` | optional HTTP URL | internal | Override for a non-default LangSmith API; unset uses the hosted default |
| `LANGSMITH_EXPORT_IO` | boolean; `false` | public | Local-only. When `true` with `APP_ENV=local` and tracing on, LangSmith receives the user message, assistant reply, model prompts, and completions. Token counts and estimated USD export even when this flag is false. Staging and production reject the flag. API keys, JWTs, and embedding vectors stay omitted. See [LANGSMITH_TRACING.md](./LANGSMITH_TRACING.md) and [ADR-local-langsmith-export-io.md](../adr/ADR-local-langsmith-export-io.md) |
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
| `SMART_RAG_REQUIRE_PHASE09_CANDIDATE` | `1` fails closed | public | Phase 9 Packet 1 live Compose/Supabase/artifact contract tests fail instead of skip |
| `SMART_RAG_OLD_API_IMAGE` | Docker image Id (`sha256:` hex) | public | Prior expand-compatible API image for Packet 2/7 old-slot/new-schema authenticated read/chat/upload smoke. Unset or a missing local image classifies Blocked (not a pytest skip). Must not equal the Packet 1 freeze API Id |
| `SMART_RAG_HOLDOUT_ACCESS` | boolean; `false` | public | Default denies sealed holdout labels. Packet 8 freeze refuses to run when true. Enable only for an independently SME-sealed holdout or dataset seal verify |
| `SMART_RAG_HOLDOUT_ACCESS_PURPOSE` | `packet8_immutable_holdout` or `dataset_seal_verify` | internal | Required when holdout access is enabled |
| `SMART_RAG_HOLDOUT_ACCESS_ACTOR` | safe identifier | internal | Auditable actor required when holdout access is enabled |
| `ADMIN_ALERT_SMTP_HOST` | optional hostname; empty skips SMTP | internal | Local Inbucket/Mailpit host. Unset skips mail; set `127.0.0.1` for Packet 8 proof |
| `ADMIN_ALERT_SMTP_PORT` | integer; `54325` | public | Exposed local SMTP port from `supabase/config.toml` `local_smtp.smtp_port` |
| `ADMIN_ALERT_SMTP_FROM` | email; `alerts@localhost` | public | Envelope from for metadata-only admin alerts |
| `ADMIN_ALERT_SMTP_TO` | email; `owner@localhost` | public | Owner/admin mailbox captured by Inbucket |

## Agent-only variables

These fields live on `AgentSettings` only. `AgentSettings` does not inherit
`BackendSettings`. Live Studio loads `BackendSettings` separately for JWKS
and DSNs. See [LANGGRAPH_STUDIO.md](./LANGGRAPH_STUDIO.md).

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `LANGGRAPH_STUDIO_LIVE_ENABLED` | boolean; `false` | public | Enables authenticated `query_studio_live` execution. Introspection stays unbound. Enabled without a token rejects and never synthetic-admits |
| `LANGGRAPH_STUDIO_ACCESS_TOKEN` | optional secret JWT | secret | Verified Supabase user access token for live Studio. Never a service-role key. Omitted from settings repr, logs, traces, checkpoints, and graph state. Rotate by replacing the gitignored value and restarting `langgraph dev`. Remove the variable and set live enabled to false to disable. Do not print this value |

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
| `SUPABASE_URL` | HTTP origin; required except `APP_ENV=test` | public | JWKS fetch origin. Tokens verify against `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`. Runtime Compose requires a hosted origin. `APP_ENV=test` injects the local fixture origin when unset. See local `iss` aliases below. |
| `SUPABASE_JWT_AUDIENCE` | non-empty string; `authenticated` | public | Required JWT `aud` claim |
| `JWKS_CACHE_SECONDS` | integer 1–600; `600` | public | JWKS cache TTL |
| `SUPABASE_DB_URL` | optional secret URL | secret | Server-side profile reads as `app_api`. Compose API/worker must not use the postgres superuser DSN; see `APP_RUNTIME_DB_PASSWORD`. May be a transaction pooler for short API work. |
| `APP_RUNTIME_DB_PASSWORD` | secret; required for local Compose | secret | Password for LOGIN wrapper `app_runtime`. `app_api` is NOLOGIN. See [LOCAL_RUNTIME_ROLES.md](../deployment/LOCAL_RUNTIME_ROLES.md) |
| `API_SUPABASE_DB_URL` | required secret URL for Compose | secret | Compose API transaction-pooler DSN as `app_runtime`. Interpolation fails closed if unset |
| `WORKER_SUPABASE_DB_URL` | required secret URL for Compose | secret | Compose worker session/direct DSN as `app_runtime`. Interpolation fails closed if unset |
| `LANGGRAPH_CHECKPOINT_URL` | optional secret URL | secret | Session/direct checkpointer/store DSN. Falls back to `SUPABASE_DB_URL` only when that fallback is also session/direct. Port `6543` and `pgbouncer=true` fail closed. Role `app_checkpointer`, schema `langgraph`. Runtime never auto-migrates. |
| `LIGHTRAG_DB_URL` | optional secret URL | secret | Runtime LightRAG attach. Session/direct only. Unset = unconfigured. Never schema-admin. |
| `CORS_ALLOW_ORIGINS` | comma-separated exact origins; `http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:3010,http://localhost:3010` | public | Wildcards forbidden. Never pair `*` with credentials. `:3010` is the Playwright developer-console origin so tests do not reuse Compose `:3000` |
| `API_VERSION` | `major.minor.patch`; `0.1.0` | public | Published by `GET /api/meta` |
| `SSE_SCHEMA_VERSION` | safe token; `1` | public | Published by `GET /api/meta` and the first SSE `schema` event |
| `MIN_CLIENT_VERSION` | `major.minor.patch`; `0.1.0` | public | Clients send `X-Client-Version` on new paid POST. Missing/below → 426 `client_version_unsupported` before admit. Resume GET does not require the header |
| `RETRIEVAL_CACHE_RESULT_TTL_SECONDS` | 1–300; `30` | public | ID/rank cache TTL |
| `RETRIEVAL_CACHE_PROFILE_TTL_SECONDS` | 1–3600; `300` | public | Profile/embedding cache TTL |
| `REQUEST_MAX_BODY_BYTES` | 1024–16_777_216; `1048576` | public | JSON/body cap; oversized → 413 |
| `VALKEY_TIMEOUT_SECONDS` | 0.05–2.0; `0.2` | public | Valkey connect/command timeout |
| `RATE_LIMIT_RETRY_AFTER_SECONDS` | 1–3600; `60` | public | `Retry-After` on limiter 429/503 |

Runtime Compose interpolates `${SUPABASE_URL:?set hosted SUPABASE_URL}`.
There is no `host.docker.internal:54321` fallback. Wire hosted Auth with
[`scripts/ops/wire_hosted_ingest_env.py`](../../scripts/ops/wire_hosted_ingest_env.py).
The default project `.env` is also used for that interpolation. A fixture
`SUPABASE_URL=http://127.0.0.1:54321` there overrides `.env.compose` and the
service `env_file`, so the API rejects hosted browser JWTs with 401
`unauthorized`. Start with [`scripts/dev.ps1`](../../scripts/dev.ps1) (loads
`.env.compose` into the process and refuses a loopback API Auth host) and
keep the fixture origin out of `.env` while Compose is running.
`APP_ENV=test` may omit `SUPABASE_URL` and receives the local fixture
origin. When `APP_ENV=local` and `SUPABASE_URL` is one of the two local
fixture origins, FastAPI accepts `iss`
`http://127.0.0.1:54321/auth/v1` or
`http://host.docker.internal:54321/auth/v1`. Signature, `kid`, and `alg`
still verify against the configured JWKS URL. Hosted laptop runtime uses
the hosted origin (no local `iss` alias). Staging and production never
expand aliases. Do not mutate `GOTRUE_JWT_ISSUER` to paper over this split.
See [IDENTITY_PROPAGATION.md](../security/IDENTITY_PROPAGATION.md),
[ADR-hosted-runtime-local-test-fixture.md](../adr/ADR-hosted-runtime-local-test-fixture.md),
and [demo-local-ingest-aws-ask.md](../runbooks/demo-local-ingest-aws-ask.md).

`X-Client-Version` is a request header, not an environment variable. New paid
`POST /conversations/{conversation_id}/messages` must send a semver-like value
greater than or equal to `MIN_CLIENT_VERSION`. See [SSE.md](../api/SSE.md).

Phase 6 packet 1 query admission still uses
`QUERY_ADMISSION_RATE_MAX_ATTEMPTS=20` / 60s as engineering defaults. Packet 5
classifies that bucket as `COST_MUTATION` (Valkey then Postgres, never
fail-open).

## Local Auth MFA (dormant provider capability)

Application authorization no longer requires TOTP or `aal2`. Owner, admin,
and `upload_enabled` callers may upload and offboard at ordinary
authenticated assurance. Supabase Auth may still expose dormant TOTP
settings; they must not authorize. Historical local TOTP config:

```toml
[auth.mfa]
max_enrolled_factors = 10

[auth.mfa.totp]
enroll_enabled = true
verify_enabled = true
```

Restart Auth after changing that file: `npx supabase stop && npx supabase start`.
Do not `db reset`. Playwright uses origin `http://127.0.0.1:3010`, which is
listed in `additional_redirect_urls`. Local upload reserve still returns
`signed_url=null` (CloudFront is Phase 10).

## Worker-only variables

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `WORKER_ONCE` | boolean; `false` | public | Exit after one poll/claim cycle |
| `ALLOW_INPROCESS_PARSER` | boolean; `false` | public | Test-only in-process parser. Requires `APP_ENV=test`. Worker start still refuses this flag when Storage Admin is in the process |
| `SUPABASE_DB_URL` | optional secret URL | secret | Worker-role session/direct Postgres DSN for claim/heartbeat |
| `WORKER_INSTANCE_ID` | string; `worker-local` | internal | Lease owner identifier for this process |
| `JOB_LEASE_SECONDS` | integer 30–3600; `300` | public | Claim and heartbeat lease duration |
| `JOB_HEARTBEAT_INTERVAL_SECONDS` | integer 10–900; `60` | public | Heartbeat cadence while a job is leased |
| `JOB_POLL_INTERVAL_SECONDS` | integer 1–60; `5` | public | Idle delay between queue polls |
| `WORKER_CONCURRENCY` | integer 1–8; `2` | public | Maximum concurrently processed ingestion jobs |
| `LANGGRAPH_CHECKPOINT_URL` | optional secret URL | secret | Checkpointer/store DSN; defaults to `SUPABASE_DB_URL` only when that URL is session/direct. Role `app_checkpointer`, schema `langgraph`. Transaction pooler DSNs fail closed. Runtime never auto-migrates. |
| `SMART_RAG_PROMPT_ENV` | `dev`, `staging`, or `prod`; `dev` | public | Prompt registry promotion. Unknown ids fail closed. See [prompts/CHANGELOG.md](../../apps/agents/src/smart_rag_agents/prompts/CHANGELOG.md) |
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
tracing is off. Local [LANGGRAPH_STUDIO.md](./LANGGRAPH_STUDIO.md) uses the
same key only to attach the hosted Studio UI; it does not enable tracing.
Backend Packet 4+ reads `SUPABASE_URL` /
JWKS settings through `BackendSettings`. Privileged secrets
`SUPABASE_AUTH_ADMIN_SECRET` and `SUPABASE_STORAGE_ADMIN_SECRET` are never
declared on `SharedSettings`, `BackendSettings`, `WorkerSettings`, or
`AgentSettings`. Auth Admin loads through `smart_rag_api.auth_admin`. Storage
Admin loads through `smart_rag_api.storage_admin` (API) and
`smart_rag_worker.privileged_storage` (worker).

## Frontend public variables

Browser bundles may only contain publishable values. See
[THIN_DEVELOPER_UI.md](../frontend/THIN_DEVELOPER_UI.md).

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | HTTP origin; `http://127.0.0.1:8000` | public | FastAPI origin for Bearer fetch SSE. Must be supplied as a Docker **build-arg** when building the frontend image; runtime env does not rewrite the Next.js bundle. |
| `NEXT_PUBLIC_SUPABASE_URL` | HTTP origin | public | Browser-direct Auth. Never a service-role URL. Docker image **build-arg**. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | publishable anon key | public | Browser Auth only. Never the service role. Docker image **build-arg**. |

`GET /health/ready` is bounded (Postgres and checkpointer probes use a 1s connect timeout). The browser client aborts the public probe after 8000ms (`HEALTH_READY_TIMEOUT_MS`).

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

See [QUALITY_TARGETS.md](../QUALITY_TARGETS.md), [LOCAL_SETUP.md](./LOCAL_SETUP.md),
[LANGGRAPH_STUDIO.md](./LANGGRAPH_STUDIO.md),
[Phase 1 foundation evidence](./phase-01-foundation-evidence.md),
[docs index](../README.md).
