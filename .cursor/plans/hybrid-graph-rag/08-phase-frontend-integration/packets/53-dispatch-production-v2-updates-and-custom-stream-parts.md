---
phase: 8
packet: 53
status: pending
title: "Dispatch production v2 updates and custom stream parts"
requirement_ids: [P08-53]
---

# Packet 53 — Dispatch production v2 updates and custom stream parts

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BEP-06` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-31, P08-49, and P08-52 complete.

## Allowed outputs

sse/stream_dispatch.py and minimal langgraph_executor.py edits.

## Forbidden outputs

Runtime logic in executors.py. Backend sleeps or forced paints. Restarting the graph on resume.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Switch production astream to updates+custom v2. Parse each part, persist derived catalog events one at a time after the current commit-before-persist rule, honor cancel, and preserve close/terminal/settlement.

## Acceptance checks

Ordering test proves node started, optional tools, node completed/failed, verify completed, verified token_delta, one terminal. Cancel after started persists partial timeline. Reconnect does not invoke the provider again.

## Negative tests

token_delta before verify_answer fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if commit-before-derived-event cannot be preserved.

## Required evidence

Append `P08-53` (`BEP-06`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
