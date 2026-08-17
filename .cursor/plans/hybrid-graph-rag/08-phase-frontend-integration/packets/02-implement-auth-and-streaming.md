---
phase: 8
packet: 2
status: complete
title: "Implement SSR Auth, audited MFA recovery/permission states, API-version handshake, typed API clients, query state, safe Bearer POST streaming, reconnect, and idempotency UX. Match frame 01's transactional sign-in and frame 03's gated owner setup where approved; fill the absent sign-up, reset/callback, MFA enrollment/challenge/lost-factor recovery, invitation/team entry, upload-MFA denial, and incompatible-client surfaces from real contracts rather than design mocks."
requirement_ids: [P08-02]
---

# Packet 2 — Implement SSR Auth, audited MFA recovery/permission states, API-version handshake, typed API clients, query state, safe Bearer POST streaming, reconnect, and idempotency UX. Match frame 01's transactional sign-in and frame 03's gated owner setup where approved; fill the absent sign-up, reset/callback, MFA enrollment/challenge/lost-factor recovery, invitation/team entry, upload-MFA denial, and incompatible-client surfaces from real contracts rather than design mocks.

Read the [Phase 8 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- `P08-01` provides approved primitives and shell.
- Phase 2/6 Auth, compatibility, OpenAPI, SSE, ownership, idempotency, and audit contracts are implemented and typed.
- Phase 7 mapping covers delivered frames 01/03 and every absent auth/compatibility surface.

## Allowed outputs

- Real `@supabase/ssr` Auth flows, typed API/query clients, compatibility admission, streaming/reconnect UX, components, routes, tests, and documentation.
- Gap-fill surfaces using approved primitives and evidence.

## Forbidden outputs

- Mock/random auth, test bypass in production, privileged keys in the browser, or client-only authorization.
- Paid submission before compatibility acceptance, duplicate paid runs, unordered resume, raw internal errors, or generated inline scripts.
- Unmapped recovery, invitation, MFA, upload-permission, or compatibility behavior.

## Ordered actions

1. Implement sign-in/up, Google OAuth, forgot/reset/callback, invitation acceptance, owner setup, disabled/revoked-session handling, and team entry with Supabase SSR Auth.
2. Implement MFA enrollment/challenge and the audited Phase 2 lost-factor identity-reverification, session-revocation, recovery, and re-enrollment procedure, including upload-MFA denial.
3. Implement the startup API/SSE/min-client handshake and block incompatible clients before any paid submission.
4. Generate/use typed API clients and TanStack Query state with safe Bearer-authenticated requests and server-enforced roles.
5. Implement idempotent Bearer POST streaming, ordered additive event handling, heartbeats, cancellation, reconnect/resume by sequence, unknown-event tolerance, and one terminal state.
6. Preserve approved frame 01/03 behavior and document primitive-based solutions for every missing auth/compatibility frame.

## Acceptance checks

- All required Auth/MFA/recovery/invitation/session/upload-permission journeys use real contracts and auditable server behavior.
- Minimum-client rejection occurs before paid work; unknown additive SSE events do not break an active answer.
- Retries/reconnects reuse one run, apply monotonic sequences, and never duplicate paid submission.
- Frame 01/03 traceability and all absent-surface gap decisions are evidenced.

## Negative tests

- Forge roles, reuse revoked sessions, bypass MFA upload gates, replay callbacks, repeat idempotency keys, reorder/duplicate SSE events, disconnect/reconnect, cancel, and inject unknown additive events.
- Simulate handshake failure, client below minimum, API deploy skew, sanitized server errors, and provider/FastAPI rate ownership.
- Scan for service-role keys, test-auth bypass, random auth, placeholder links, static diagnostics, inline scripts, and raw error leakage.

## Stop routes

- Stop and return missing/incompatible Auth/API/SSE contracts to their owning phase.
- Fail closed when compatibility, identity reverification, authorization, or paid-work idempotency cannot be proven.

## Required evidence

Append `P08-02` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): frame/gap traceability, real contract versions, auth/MFA/audit tests, handshake-before-spend proof, streaming sequence/idempotency/reconnect results, security scans, and blockers.
