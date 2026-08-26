---
phase: 8
packet: 81
status: pending
title: "Split shell and admin CSS owners"
requirement_ids: [P08-81]
---

# Packet 81 — Split shell and admin CSS owners

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-19` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-64 and P08-74 complete.

## Allowed outputs

app-shell layout/navigation/topbar modules and admin shell/tables/curation modules.

## Forbidden outputs

Mixing responsive fixes into the move or duplicating selectors.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Each CSS module <=280. Update geometry, shell, administration, 390px, and desktop visual tests without blessing collisions.

## Acceptance checks

No concern-owned CSS over 300 physical lines in these owners.

## Negative tests

A hydration-breaking class rename fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if UX-01 markup is still unstable.

## Required evidence

Append `P08-81` (`MOD-19`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
