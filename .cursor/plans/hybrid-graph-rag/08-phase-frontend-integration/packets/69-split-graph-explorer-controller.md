---
phase: 8
packet: 69
status: pending
title: "Split graph explorer controller"
requirement_ids: [P08-69]
---

# Packet 69 — Split graph explorer controller

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-16` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45 complete. Before keyboard graph behavior changes.

## Allowed outputs

graph/hooks/use-graph-explorer.ts and small results/inspector components.

## Forbidden outputs

Changing the 12-chip bound or splitting list/canvas selection into two callbacks.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move search, chip selection, inspect mutation, and stale-result guards. graph-explorer.tsx exits <=220 lines.

## Acceptance checks

graph-explorer and core-rag-surfaces tests pass.

## Negative tests

A stale inspect writing into a new search fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if React Flow imports would need a behavior change.

## Required evidence

Append `P08-69` (`MOD-16`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
