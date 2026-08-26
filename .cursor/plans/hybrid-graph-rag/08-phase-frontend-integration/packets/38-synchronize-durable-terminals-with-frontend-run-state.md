---
phase: 8
packet: 38
status: pending
title: "Synchronize durable terminals with frontend run state"
requirement_ids: [P08-38]
---

# Packet 38 — Synchronize durable terminals with frontend run state

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `P08B-03` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-35 complete. Chat reducer and consumeSse are inspectable.

## Allowed outputs

Mapper/service terminal sequencing and frontend applySseFrame/consumeSse/run-controller fixes.

## Forbidden outputs

Polling over the bug, clearing durable partial, or inventing a client terminal.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Exactly one catalog terminal is sequenced. deadline is diagnostic before partial. Frontend treats every catalog terminal as terminal, first-terminal-wins, publishes terminal even when it shares a byte chunk, stops reconnect, and does not show running after durable partial.

## Acceptance checks

Reducer, consumeSse, chat-app, lifecycle, and resume tests pass for deadline-partial, cancel, error, completed, split frames, and reload.

## Negative tests

UI remaining running after durable partial fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a second protocol terminal would be required to fix the UI.

## Required evidence

Append `P08-38` (`P08B-03`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
