---
title: Foundation configuration contract
owner: engineering-lead
status: verified
last-reviewed: 2026-08-12
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
| `PARADEDB_URL` | optional URL | secret | May contain credentials; not connected during Packet 4 |
| `CRAWL_PROXY_URL` | optional HTTP URL | internal | Private deny-by-default proxy endpoint |

## Backend-only variables

| Variable | Type / default | Security | Contract |
| --- | --- | --- | --- |
| `API_BIND_HOST` | non-empty string; `0.0.0.0` | public | Uvicorn bind address used only by the console entrypoint |
| `API_BIND_PORT` | integer 1–65,535; `8000` | public | Uvicorn container port |

Worker and agent settings currently add only a stable, non-environment service
name. Queue, ingestion, retrieval, auth, RLS, and graph settings are not
implemented in this packet.

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
planned placeholders. Packet 4 does not read them or claim their integrations.

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
