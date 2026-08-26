---
phase: 8
packet: 48
status: pending
title: "Add additive SSE progress catalog fields"
requirement_ids: [P08-48]
---

# Packet 48 — Add additive SSE progress catalog fields

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BEP-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-24, P08-32, P08-35, and P08-40 complete. P06-16 is linked.

## Allowed outputs

sse catalog, mapping/contracts.py, types/sse.ts wire names, and catalog tests. Additive docs notes only as needed for field names.

## Forbidden outputs

Producers emitting the new events. Major handshake bump unless this packet explicitly changes it. Forbidden payload keys.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Add optional status.phase started|completed|failed and tool_progress {tool_key, phase}. Keep extra-forbid catalog. Cap stage/tool_key at 64 if unbounded. Synchronize frontend known-event union.

## Acceptance checks

Legal phases validate; others reject. Legacy status without phase validates. Unknown event types still fail. Protocol tests pass.

## Negative tests

A catalog payload with query/result/error keys succeeding fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if extra-forbid cannot remain closed.

## Required evidence

Append `P08-48` (`BEP-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
