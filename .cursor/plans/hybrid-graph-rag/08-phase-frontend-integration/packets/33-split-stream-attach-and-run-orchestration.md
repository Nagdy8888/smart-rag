---
phase: 8
packet: 33
status: pending
title: "Split stream attach and run orchestration"
requirement_ids: [P08-33]
---

# Packet 33 — Split stream attach and run orchestration

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BMOD-07` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-24 complete. service.py is inspectable.

## Allowed outputs

sse/run_access.py, sse/run_orchestration.py, and service.py public attach/iter_frames orchestration.

## Forbidden outputs

Module globals, progress events, or persist-before-flush changes.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Extract admitted-run ownership/readability/cancel notification and start-once/executor/heartbeat helpers. Keep SseStreamService construction and iter_frames in service.py. service.py <=300 physical lines.

## Acceptance checks

One start, heartbeat, cancel, attach/replay, and settlement behavior are unchanged.

## Negative tests

A second start or lost cancel notification fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if persist-before-flush cannot be preserved.

## Required evidence

Append `P08-33` (`BMOD-07`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
