---
phase: 8
packet: 71
status: pending
title: "Coalesce stream publications without losing events"
requirement_ids: [P08-71]
---

# Packet 71 — Coalesce stream publications without losing events

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `PER-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-44 and P08-55 complete.

## Allowed outputs

sse-consume.ts, use-chat-run.ts, and tests. Optional onCursor after onState.

## Forbidden outputs

Dropping intermediate progress history. Applying a short timeout to long-lived SSE.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Parse all complete frames per reader.read(), reduce synchronously, onState once per batch or at terminal. Heartbeat-only batches update cursor via onCursor without React state. Resume must not regress.

## Acceptance checks

Tests cover multi-frame chunks, split frames, mid-batch terminal, foreign run, identical reconstructed answer, and heartbeat-only no React publication.

## Negative tests

Losing a started node because React was coalesced fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if first-terminal-wins would be lost.

## Required evidence

Append `P08-71` (`PER-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
