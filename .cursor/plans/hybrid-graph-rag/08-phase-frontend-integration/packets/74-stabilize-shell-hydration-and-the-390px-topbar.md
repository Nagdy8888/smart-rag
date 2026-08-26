---
phase: 8
packet: 74
status: pending
title: "Stabilize shell hydration and the 390px topbar"
requirement_ids: [P08-74]
---

# Packet 74 — Stabilize shell hydration and the 390px topbar

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `UX-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45 complete. layout-preferences.ts exists.

## Allowed outputs

use-layout-preference.ts, app-shell/nav/readiness/CSS, and visual-routes waits.

## Forbidden outputs

suppressHydrationWarning as the fix. Storing auth in the preference. Updating baselines to accept a collision.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Server and first client snapshot use defaultNavExpanded(). useSyncExternalStore reads persisted preference after hydration. At 390px hide duplicate brand, truncate title, keep >=36px targets, compact accessible readiness.

## Acceptance checks

Zero AppShell hydration errors. 390px and desktop captures wait for readiness and route-data, not only #main.

## Negative tests

A vertical single-letter Checking column fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if the storage key contract cannot be reused.

## Required evidence

Append `P08-74` (`UX-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
