---
phase: 8
packet: 78
status: pending
title: "Provide keyboard-equivalent graph selection"
requirement_ids: [P08-78]
---

# Packet 78 — Provide keyboard-equivalent graph selection

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `UX-05` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-69 complete. Pinned React Flow version is verified from primary docs.

## Allowed outputs

graph-canvas, graph-explorer, graph-list-fallback, and tests.

## Forbidden outputs

Enabling edit/drag/connect. Claiming canvas parity if focus is unreliable.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Keep List as the canonical accessible default. If canvas node focus works, Enter/Space calls the same onSelect. Otherwise label Canvas supplementary and provide Open accessible list.

## Acceptance checks

List selection, inspector focus/return, and no edit affordances. Canvas path is either keyboard-proven or explicitly supplementary.

## Negative tests

Pointer-only selection with no list path fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if the pinned React Flow docs cannot be verified.

## Required evidence

Append `P08-78` (`UX-05`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
