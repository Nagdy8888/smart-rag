---
phase: 8
packet: 12
status: complete
title: "Remove frontend/provider MFA and finish single-factor Auth"
requirement_ids: [P08-12]
---

# Packet 12 — Remove frontend/provider MFA and finish single-factor Auth

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-11 backend/database MFA enforcement is removed on this branch and not yet merged alone.

## Allowed outputs

Delete MFA routes/helpers/tests, local provider config via documented settings, managed runbook, remaining Auth polish.

## Forbidden outputs

Direct SQL factor deletion. Shipping a disabled Google button. Merging P08-11 without this packet. Starting UI surface packets before this evidence.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-12 — Remove frontend/provider MFA and finish single-factor Auth

Purpose: immediately complete the approved MFA removal transaction by deleting TOTP product behavior and proving the remaining single-factor Auth journeys.

Primary files:

- [`supabase/config.toml`](supabase/config.toml)
- Auth routes/components under `apps/frontend/src/app/(auth)` and `apps/frontend/src/components/auth`
- helpers under `apps/frontend/src/lib/auth`, including current `totp-qr.ts` and `mfa-recovery.ts`
- invitation acceptance routing, Auth tests, action inventory, frontend/security/Auth docs, managed-provider runbook, ADR, and Phase 8 evidence.

Implementation:

- Before editing configuration, verify the pinned Supabase Auth configuration/admin API in current primary documentation. Do not guess a TOML key.
- Remove `/mfa/enroll` and `/mfa/challenge` routes, forms, QR generation, challenge verification, recovery helpers/copy, navigation, callbacks, and unavailable-gap routing.
- Delete MFA-only files/tests only after reference search proves no retained import remains.
- Remove `mfa_enrolled`, assurance level, factor lists, and MFA-required errors from frontend state and rendering.
- Disable TOTP enrollment/challenge in local Supabase configuration only through a documented supported setting.
- For managed Supabase, write a dry-run-first operator procedure using only documented provider settings/admin APIs. Never remove factors with direct SQL. If safe enumeration/unenrollment is unavailable, leave provider residue dormant and state that limitation honestly.
- Keep and polish email/password sign-in, sign-up, forgot/reset, callback, invitation acceptance, and sign-out. Move invitation acceptance into the Auth layout.
- Omit Google OAuth while disabled; do not render a disabled button.
- Preserve callback allow-listing, cookie refresh, revoked-session handling, generic production errors, and the absence of anonymous/test-auth bypasses.
- Update the action inventory and maintained docs; do not rewrite historical reviews or migrations.

Acceptance tests:

- Sign-in, sign-up, reset/callback, invitation acceptance, revoked-session return, and sign-out pass without an MFA route or challenge.
- No production route, import, action, copy, state, test, or provider-local config enables/expects TOTP/MFA.
- No Supabase internal message is rendered verbatim.
- Managed-provider handling is documented with prerequisites, dry run, verification, rollback, and honest residue limits.
- P08-11 backend/RLS checks plus frontend Auth, type, lint, unit, route, docs, and plan-integrity checks pass together.
- The two-packet MFA transaction is complete before P08-13 starts.

## Acceptance checks

Sign-in/up/reset/callback/invitation/sign-out work with no MFA route. No production import expects TOTP. Docs record honest provider residue.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a documented provider setting/admin API cannot be verified. Leave residue dormant rather than inventing deletion SQL.

## Required evidence

Append `P08-12` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
