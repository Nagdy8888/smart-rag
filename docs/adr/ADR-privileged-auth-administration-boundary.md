---
title: ADR — Privileged Auth administration boundary
adr_id: ADR-privileged-auth-administration-boundary
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-13
approver: "Phase 2 Packet 4 implementation"
approval_date: "2026-08-13"
---

# ADR: Privileged Auth administration boundary

## Context

Supabase Auth Admin operations (invitations, factor administration, global session
revocation, disable/offboarding) require a broad credential equivalent to
`service_role`. That secret must never load into general FastAPI, worker,
frontend, health, or `SharedSettings` paths.

## Decision

1. Introduce an isolated module tree:
   `apps/backend/src/smart_rag_api/auth_admin/`.
2. Only this module may read `SUPABASE_AUTH_ADMIN_SECRET` through
   `PrivilegedAuthSettings` (`auth_admin/settings.py`).
3. General API JWT verification uses asymmetric JWKS only
   (`packages/core/src/smart_rag_core/security/jwks.py`); no JWT shared secret.
4. Future dedicated worker/admin processes may import the same boundary module;
   they must not reuse `SharedSettings` for the Auth Admin secret.
5. Health/readiness endpoints and structured logs must never expose or enumerate
   privileged Auth settings.

## Consequences

- Invitation delivery, MFA factor reset, global session revocation, and the
  immediate security subset of offboarding are implemented only under
  `auth_admin/`.
- Invitation actors and domains are re-resolved from authoritative database
  rows. Provider delivery failure revokes the application invitation token.
- Lost-factor recovery requires a distinct active owner/admin at AAL2 and a
  bounded external verification reference. Completion deletes every provider
  factor and globally logs out the subject before committing completion.
- Offboarding immediately disables the profile, removes upload capability,
  revokes sessions, and bumps the authorization snapshot. Export/purge remains
  explicitly deferred to its later owner.
- Contract tests scan `SharedSettings`, health handlers, and general settings
  loaders for `service_role` / Auth Admin secret exposure.
- Managed key rollover remains a runbook + staging gate; local CLI cannot rotate
  signing keys without Management API credentials.

## Related documents

- [AUTH_RATE_LIMIT_OWNERSHIP.md](../security/AUTH_RATE_LIMIT_OWNERSHIP.md)
- [SUPABASE_JWKS_ROLLOVER.md](../runbooks/SUPABASE_JWKS_ROLLOVER.md)
- [IDENTITY_PROPAGATION.md](../security/IDENTITY_PROPAGATION.md)
