---
phase: 8
packet: 50
status: pending
title: "Emit truthful node-start progress from bound wrappers"
requirement_ids: [P08-50]
---

# Packet 50 — Emit truthful node-start progress from bound wrappers

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BEP-03` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-27 and P08-49 complete.

## Allowed outputs

query/streaming/progress.py and graph.py wiring only.

## Forbidden outputs

Wrapping studio seed/emit nodes. Emitting completed from the wrapper. Catching node exceptions. Backend SSE imports in agents.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Wrap the exact production stage keys. Emit get_stream_writer()({kind: node_start, stage}) immediately before substantive work. Skip closed-state no-ops. Updates remain completion proof.

## Acceptance checks

Start precedes the same node update. Skipped route nodes emit zero starts. Payload has only kind and stage. Route tests remain identical.

## Negative tests

A phantom start for a skipped node fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if wrappers would force graph.py over 300 lines; move construction instead.

## Required evidence

Append `P08-50` (`BEP-03`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
