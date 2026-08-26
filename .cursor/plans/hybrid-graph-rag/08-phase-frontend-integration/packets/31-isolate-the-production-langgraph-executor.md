---
phase: 8
packet: 31
status: pending
title: "Isolate the production LangGraph executor"
requirement_ids: [P08-31]
---

# Packet 31 — Isolate the production LangGraph executor

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BMOD-05` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-28 through P08-30 complete.

## Allowed outputs

sse/langgraph_executor.py and an executors.py compatibility barrel <=100 physical lines exporting QueryRunExecutor, FixtureQueryRunExecutor, and LangGraphQueryRunExecutor.

## Forbidden outputs

Changing stream_mode in this move-only packet. Putting runtime logic back into executors.py.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move LangGraphQueryRunExecutor into langgraph_executor.py. Keep existing stream_mode='updates' during the move. Every production module <=300 physical lines.

## Acceptance checks

Lifecycle, verified-final, settlement, event-store, and resume tests pass. executors.py is a facade.

## Negative tests

A missing compatibility export fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if verified-final tests fail during the move.

## Required evidence

Append `P08-31` (`BMOD-05`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
