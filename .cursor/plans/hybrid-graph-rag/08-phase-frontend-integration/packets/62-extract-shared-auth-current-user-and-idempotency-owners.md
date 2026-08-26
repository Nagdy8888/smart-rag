---
phase: 8
packet: 62
status: pending
title: "Extract shared auth, current-user, and idempotency owners"
requirement_ids: [P08-62]
---

# Packet 62 — Extract shared auth, current-user, and idempotency owners

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-18` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-41 through P08-44 complete. Before MOD-09/MOD-10 owners.

## Allowed outputs

lib/idempotency.ts, lib/auth/use-api-auth.ts, lib/hooks/use-current-user.ts, and tests.

## Forbidden outputs

Creating a Supabase client or refreshing tokens in useApiAuth. Generating a new idempotency key inside a retry.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move crypto.randomUUID helpers to newIdempotencyKey(). useApiAuth memoizes {accessToken} from useSession. useCurrentUser owns session-scoped /me. Server /me remains role authority.

## Acceptance checks

Stable object identity, null signed-out auth, subject-scoped /me, revoked-session failure, one /me for multiple consumers, key reuse across retry.

## Negative tests

A new key on retry fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if duplicate /me keys cannot be characterized first.

## Required evidence

Append `P08-62` (`MOD-18`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
