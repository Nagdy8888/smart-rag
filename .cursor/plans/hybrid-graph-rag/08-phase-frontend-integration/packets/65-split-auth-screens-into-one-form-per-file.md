---
phase: 8
packet: 65
status: pending
title: "Split auth screens into one form per file"
requirement_ids: [P08-65]
---

# Packet 65 — Split auth screens into one form per file

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-11` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-62 complete.

## Allowed outputs

auth/{auth-banners,sign-in-form,sign-up-form,forgot-password-form,reset-password-form,invitation-accept-form}.ts(x) and an exports-only auth-screens.tsx.

## Forbidden outputs

Secret logging or changing PKCE/invitation/Supabase client ownership.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Each form <=150 lines. Expand tests to forgot, reset, invitation, environment-missing, and handshake failures.

## Acceptance checks

Existing plus new auth-screen tests pass. Barrel is exports-only.

## Negative tests

A dropped invitation accept path fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if PKCE exchange would move to the client form incorrectly.

## Required evidence

Append `P08-65` (`MOD-11`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
