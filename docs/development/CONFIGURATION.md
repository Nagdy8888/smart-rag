---
title: Foundation configuration contract
owner: engineering-lead
status: verified
last-reviewed: 2026-08-14
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
| `MOCK_MODEL_FIXTURE_ID` | safe identifier; `phase-1-foundation-v1` | internal | Included in fixture provenance; does not imply retrieval |
| `MODEL_INPUT_MAX_CHARS` | integer 1–65,536; 16,384 | public | Deployable gateway input bound |
| `VALKEY_LIMITS_URL` | optional URL | secret | May contain credentials; not connected during Packet 4 |
| `VALKEY_CACHE_URL` | optional URL | secret | May contain credentials; not connected during Packet 4 |
| `PARADEDB_URL` | optional URL | secret | Worker/API ParadeDB DSN. Packet 8 host pytest uses `docker-compose.packet8.yml` loopback `:54329` |
| `CRAWL_PROXY_URL` | optional HTTP URL | internal | Private deny-by-default proxy endpoint. Packet 8 overlay publishes `http://127.0.0.1:18080` |
| `CLAMAV_HOST` / `CLAMAV_PORT` | hostname / Packet 8 overlay `13310` | internal | Worker uses Compose DNS `clamav:3310`. Packet 8 overlay publishes host `13310` |
| `SMART_RAG_REQUIRE_CLAMAV` | `1` fails closed | public | Contract tests fail instead of skip when ClamAV is down |
| `SMART_RAG_REQUIRE_CRAWL_PROXY` | `1` fails closed | public | Live proxy overlay tests fail instead of skip |
| `SMART_RAG_REQUIRE_JOB_INTEGRATION` | `1` fails closed | public | Postgres job/checkpointer tests fail instead of skip |
| `ADMIN_ALERT_SMTP_HOST` | optional hostname; empty skips SMTP | internal | Local Inbucket/Mailpit host. Unset skips mail; set `127.0.0.1` for Packet 8 proof |
| `ADMIN_ALERT_SMTP_PORT` | integer; `54325` | public | Exposed local SMTP port from `supabase/config.toml` `local_smtp.smtp_port` |
| `ADMIN_ALERT_SMTP_FROM` | email; `alerts@localhost` | public | Envelope from for metadata-only admin alerts |
| `ADMIN_ALERT_SMTP_TO` | email; `owner@localhost` | public | Owner/admin mailbox captured by Inbucket |

## Backend-only variables

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `API_BIND_HOST` | non-empty string; `0.0.0.0` | public | Uvicorn bind address used only by the console entrypoint |
| `API_BIND_PORT` | integer 1–65,535; `8000` | public | Uvicorn container port |

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

Agent settings currently add only a stable, non-environment service name.
Queue, ingestion, retrieval, and graph settings remain owned by later phases.

## Managed proof-operation variables

The destructive JWKS rollover script loads its values through
`JwksRolloverSettings`, not direct process-environment reads:

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `SUPABASE_ACCESS_TOKEN` | required secret | secret | Short-lived Management API token |
| `SUPABASE_PROJECT_REF` | required safe identifier | internal | Explicit managed project target |
| `SUPABASE_MANAGED_URL` | required HTTP URL | internal | Managed Auth/JWKS origin |
| `SUPABASE_ANON_KEY` | required key | secret | Publishable Auth key redacted from settings representations |

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

`LANGSMITH_API_KEY`, `SUPABASE_URL`, and `SUPABASE_ANON_KEY` remain commented,
planned placeholders for Compose. Backend Packet 4+ reads `SUPABASE_URL` /
JWKS settings through `BackendSettings`. Privileged secrets
`SUPABASE_AUTH_ADMIN_SECRET` and `SUPABASE_STORAGE_ADMIN_SECRET` load only
inside `smart_rag_api.auth_admin` and `smart_rag_api.storage_admin`
respectively—never through `SharedSettings`.

## Failure and security behavior

- Real-model mode without `OPENAI_API_KEY` fails startup.
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
