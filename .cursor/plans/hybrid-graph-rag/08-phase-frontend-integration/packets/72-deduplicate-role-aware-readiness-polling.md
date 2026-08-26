---
phase: 8
packet: 72
status: pending
title: "Deduplicate role-aware readiness polling"
requirement_ids: [P08-72]
---

# Packet 72 — Deduplicate role-aware readiness polling

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `PER-02` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-43 and P08-62 complete.

## Allowed outputs

hooks/use-console-readiness.ts, query-keys update, readiness-indicator and usage-panel consumers.

## Forbidden outputs

Raw token or UI-derived role in the key. Treating readiness as authorization.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Canonical key ['console-ready', sessionScope, role ?? 'pending'] via sessionQueryKeys. Role from /me. staleTime 30000, refetchInterval 15000, no background refetch. Public signed-out readiness stays separate.

## Acceptance checks

One request per key per polling interval with shell/chat/usage mounted together. Role transition creates a new key. Sign-out clears private readiness.

## Negative tests

Two polling loops for the same session-role fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if operator readiness would run without server owner/admin role.

## Required evidence

Append `P08-72` (`PER-02`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
