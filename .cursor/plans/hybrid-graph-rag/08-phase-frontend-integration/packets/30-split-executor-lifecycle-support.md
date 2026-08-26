---
phase: 8
packet: 30
status: pending
title: "Split executor lifecycle support"
requirement_ids: [P08-30]
---

# Packet 30 — Split executor lifecycle support

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BMOD-04` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-29 complete.

## Allowed outputs

sse/stream_lifecycle.py, sse/answer_persistence.py, and a <=100-line executor_support.py compatibility surface.

## Forbidden outputs

Swallowing persistence errors or reordering commit/RLS/first-terminal behavior.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Split close/termination/token-usage helpers from terminal commit, optional summary, and assistant-message persistence. Keep cancellation, first-terminal, summary budget, and assistant-message idempotency.

## Acceptance checks

Lifecycle and settlement tests pass. executor_support.py <=100 physical lines if retained.

## Negative tests

Duplicate assistant persistence or a swallowed persist error fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if commit order cannot be preserved without a behavior change.

## Required evidence

Append `P08-30` (`BMOD-04`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
