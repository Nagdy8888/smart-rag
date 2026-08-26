---
phase: 8
packet: 67
status: pending
title: "Split overlay CSS and primitives"
requirement_ids: [P08-67]
---

# Packet 67 — Split overlay CSS and primitives

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-13` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-66 complete.

## Allowed outputs

ui/styles/overlays.module.css for sheet, confirm, command menu, menu, popover, and drawer.

## Forbidden outputs

Focus-behavior changes (owned by P08-77). Remaining ui.module.css concern over 300 lines.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move overlay selectors without visual change. Run primitive, geometry, and visual tests.

## Acceptance checks

ui.module.css has no remaining concern over 300 physical lines.

## Negative tests

Duplicated overlay selectors fail the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if UX-04 behavior would be required to finish the move.

## Required evidence

Append `P08-67` (`MOD-13`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
