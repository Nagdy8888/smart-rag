---
title: Protected migration and privileged credentials
owner: engineering-lead
status: proven-local / unverified-managed
last-reviewed: 2026-08-16
audience: engineering, security, ops
phase_packet: Phase 2 Packet 6
---

# Protected migration credentials

## Local custody (proven)

| Item | Local practice |
| --- | --- |
| Bootstrap / migration DB password | Developer `.env` / `.env.compose` (**gitignored**) |
| Supabase CLI | `npx supabase db reset` / `migration up` using local stack credentials |
| Runtime containers | `api` / `worker` / `frontend` receive only least-privilege URLs (`app_api`, BM25 reader/writer, Valkey) |
| Auth Admin secret | Isolated boundary module only (`apps/backend/.../auth_admin/`); absent from `SharedSettings` / `BackendSettings` |
| Storage Admin secret | Isolated boundary modules only (`apps/backend/.../storage_admin/` and worker `privileged_storage`); absent from `SharedSettings` / `BackendSettings` / `WorkerSettings` / `AgentSettings` |
| `service_role` | Never declared on general runtime settings; never shipped to frontend |

Contract: `tests/contract/test_privileged_secrets_absent.py` plus Packet 4/5 secret-scan tests. That contract inspects runtime settings **field names and env aliases only**; isolated package or loader names such as `storage_admin` / `load_privileged_storage_settings` are not treated as secret declarations.

## Runtime must not load bootstrap

General API/worker/frontend processes must not read:

- migration/bootstrap Postgres superuser URLs
- `SUPABASE_SERVICE_ROLE_KEY` / Auth Admin / Storage Admin secrets for ordinary request paths
- ParadeDB bootstrap DDL credentials (runtime uses reader/writer only)

Health endpoints must not echo privileged secret names or values.

## Managed design (Phase 10 — unverified)

Managed staging/production **design** (not implemented in Phase 2):

1. Migration credentials live in AWS Secrets Manager (or equivalent).
2. A one-shot migration job assumes GitHub OIDC → IAM role, fetches the secret, runs migrations, exits.
3. KMS/S3 Object Lock anchoring for audit exports is Phase 10.
4. Credentials are **never** stored as long-lived GitHub Actions secrets for runtime.

**Honest status:** OIDC, Secrets Manager, KMS, and Object Lock are **not provisioned**
and **not proven** in this packet. Do not treat this document as Phase 10 evidence.

## Related

- [ADR-privileged-auth-administration-boundary.md](../adr/ADR-privileged-auth-administration-boundary.md)
- [ADR-upload-capability-and-storage-privilege.md](../adr/ADR-upload-capability-and-storage-privilege.md)
- [AUDIT_CHAIN.md](./AUDIT_CHAIN.md)
