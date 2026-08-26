---
phase: 8
packet: 11
status: complete
title: "Remove backend and database MFA/AAL2 enforcement"
requirement_ids: [P08-11]
---

# Packet 11 — Remove backend and database MFA/AAL2 enforcement

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-10 protocol hardening is complete. Additive migration path is inspectable. P08-12 is the mandatory next packet.

## Allowed outputs

Additive SQL/function/policy wrappers, backend AAL2/MFA check removal, OpenAPI/types/docs/tests, compensating-control preservation.

## Forbidden outputs

Editing applied migrations. Dropping old signatures in this release. Merging without P08-12. Weakening role/RLS/JWT/rate-limit/audit controls.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-11 — Remove backend and database MFA/AAL2 enforcement

Purpose: remove server-side MFA/AAL2 authorization requirements before privileged UI surfaces are rebuilt, while preserving every non-MFA security control.

Primary files:

- one new additive Supabase migration; never edit an applied migration
- identity/auth schemas and services under `apps/backend/src/smart_rag_api`, including profile loading, upload authorization, invitation/offboarding, and security error mapping
- shared identity models under `packages/core/src/smart_rag_core/security`
- [`docs/api/openapi.foundation.json`](docs/api/openapi.foundation.json), generated/current API types, security docs, ADR, Phase 8 evidence, and focused backend/RLS tests.

Implementation:

- Remove every live backend check that requires `aal2`, `mfa_enrolled`, an enrolled factor, or an `MFA required` error for upload reserve/finalize, offboarding, document administration, or any other route.
- Keep owner/admin/member/viewer roles, upload capability, authorization-version reloads, JWT verification, revoked/disabled sessions, RLS, rate limits, audit events, destructive confirmations, and IDOR-safe errors unchanged.
- Replace AAL2-gated database functions/policies with additive versions or compatibility wrappers that preserve existing signatures during the current API major while removing only the AAL2 rejection.
- Do not edit historical migrations, mutate the managed `auth` schema directly, or drop old function signatures in this release.
- Update backend callers to use the non-MFA behavior. Remove assurance arguments only where additive compatibility permits; otherwise retain ignored deprecated parameters and document them.
- Remove MFA from `GET /me` product semantics. If deleting `mfa_enrolled` would break additive API evolution, retain it only as a deprecated compatibility field fixed to `false`; no authorization decision may read it.
- Remove MFA-specific backend HTTP/SSE errors and OpenAPI descriptions. Historical reviews and immutable migration text remain unchanged.
- This packet may leave the old optional MFA frontend visible for one feature-branch commit, but it may not be merged or followed by surface work. P08-12 is the mandatory next packet.

Acceptance tests:

- Owner/admin at ordinary authenticated assurance can upload and offboard when all non-MFA checks pass.
- Member/viewer forged upload/admin/offboard requests still fail with the same 403/404 semantics.
- No live backend path emits `MFA required`, checks `aal2`, or authorizes from `mfa_enrolled`.
- Existing JWT, revoked-session, role, capability, RLS, rate-limit, audit, IDOR, upload, and offboarding tests remain green.
- OpenAPI, generated/current types, schema tests, RLS matrix, migration checks, security docs, and plan integrity pass.
- Evidence explicitly marks P08-12 as required before any UI packet or merge.

## Acceptance checks

Owner/admin at ordinary assurance can upload/offboard when non-MFA checks pass. Member/viewer still denied. No live backend path requires aal2.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if the pinned Supabase Auth/admin contract cannot be verified from current primary docs. Do not guess TOML or mutate managed auth schema.

## Required evidence

Append `P08-11` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
