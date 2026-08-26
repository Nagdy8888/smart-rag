---
phase: 8
packet: 34
status: pending
title: "Split persistence, append, replay, and cancel helpers"
requirement_ids: [P08-34]
---

# Packet 34 — Split persistence, append, replay, and cancel helpers

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BMOD-08` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-33 complete.

## Allowed outputs

sse/event_append.py, sse/run_settlement.py, sse/replay_cancel.py, and a <=100-line service_persist.py compatibility surface.

## Forbidden outputs

Changing sequence allocation, first-terminal, RLS context, or idempotent settlement.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move sync/async append and catalog validation, schema/durable-start/worker-unavailable/reservation settlement, and terminal lookup/replay/cooperative cancel/task cleanup into owners.

## Acceptance checks

Event-store, lifecycle, settlement, heartbeat, cancel, and resume tests pass. service_persist.py <=100 if retained.

## Negative tests

A second settlement on replay fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if RLS/caller context cannot be preserved.

## Required evidence

Append `P08-34` (`BMOD-08`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
