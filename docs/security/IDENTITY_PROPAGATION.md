---
title: Identity propagation
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering, security, reviewers
---

# Identity propagation

FastAPI → Postgres identity is **explicit**, **typed**, and **transaction-pool safe**. Connection reuse must not leak caller identity between requests.

## Sequence: authenticated read via RPC

```mermaid
sequenceDiagram
  participant Browser
  participant FastAPI
  participant JWKS as Supabase JWKS
  participant DB as Postgres app_api role
  participant RPC as app.list_visible_documents

  Browser->>FastAPI: Authorization Bearer JWT
  FastAPI->>JWKS: Verify iss/aud/exp/kid/signature
  JWKS-->>FastAPI: Valid subject + session claims
  FastAPI->>DB: SELECT profiles + company_settings
  DB-->>FastAPI: role, disabled, authorization_version
  FastAPI->>RPC: caller_user_id, caller_role, authorization_version
  Note over RPC: validate_caller_context inside RPC
  RPC-->>FastAPI: ACL-filtered rows or zero rows
  FastAPI-->>Browser: Sanitized response
```

## CallerContext (core)

`packages/core/src/smart_rag_core/security/identity.py` defines the frozen Pydantic contract:

| Field | Source | Trusted from client? |
| --- | --- | --- |
| `user_id` | Verified JWT `sub` + profile FK | **Never** |
| `role` | `app.profiles.role` | **Never** |
| `authorization_version` | `app.company_settings.authorization_version` | **Never** |
| `session_id` | JWT session claim (Packet 4) | **Never** |
| `disabled` | `app.profiles.disabled_at` | **Never** |
| `upload_enabled` | `app.profiles.upload_enabled` | **Never** |
| `mfa_enrolled` | `app.profiles.mfa_enrolled` | **Never** |

FastAPI dependency stub: `apps/backend/src/smart_rag_api/dependencies/identity.py`. Packet 4 replaces header simulation with JWKS + live profile reads.

## Transaction pooling rules

| Path | Pool mode | Identity mechanism |
| --- | --- | --- |
| API RPC reads/writes | transaction (Supavisor) | RPC **arguments** only |
| LangGraph checkpointer | session/direct | dedicated `app_checkpointer` role |
| LightRAG storage | session/direct | dedicated `app_lightrag` role |
| Worker queues | transaction | job lease owner + worker role grants |

**Forbidden on transaction-pooled API paths:**

- `set_config('request.jwt.claims', …)` or other session GUC identity
- trusting client-supplied role, ACL, or authorization snapshot headers in production
- prepared statements that bind identity at prepare time without per-call validation

## RPC validation flow

```mermaid
flowchart TD
  start[RPC invoked by app_api] --> nullCheck{caller args null?}
  nullCheck -->|yes| zero[Return zero rows]
  nullCheck -->|no| roleCheck{role in enum?}
  roleCheck -->|no| zero
  roleCheck -->|yes| versionCheck{authorization_version matches live?}
  versionCheck -->|no| zero
  versionCheck -->|yes| profileCheck{profile active and role matches?}
  profileCheck -->|no| zero
  profileCheck -->|yes| acl[Apply ACL / creator-private filters]
  acl --> rows[Return authorized rows]
```

Live version is always read inside the RPC transaction from `app.company_settings`.

## Pool reuse safety test (Packet 3)

Contract tests connect as `postgres`, `SET ROLE app_api`, invoke RPCs with forged/stale context, and assert zero rows. They do **not** rely on session GUCs surviving across calls.

Packet 6 adds concurrent connection reuse tests under Supavisor transaction mode.

## Audit writer path

```mermaid
sequenceDiagram
  participant Svc as Audited service
  participant AW as app_audit_writer
  participant AE as app.audit_events

  Svc->>AW: append_audit_event(...) or INSERT policy
  AW->>AE: INSERT only
  Note over AE: UPDATE/DELETE blocked by trigger
```

## Related documents

- [AUTHORIZATION_MODEL.md](./AUTHORIZATION_MODEL.md)
- [05-database-connections.md](../architecture/05-database-connections.md)
- [Phase 2 evidence](../development/phase-02-identity-data-evidence.md)
