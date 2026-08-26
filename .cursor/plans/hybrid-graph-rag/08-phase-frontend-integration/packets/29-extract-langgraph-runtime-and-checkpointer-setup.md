---
phase: 8
packet: 29
status: pending
title: "Extract LangGraph runtime and checkpointer setup"
requirement_ids: [P08-29]
---

# Packet 29 — Extract LangGraph runtime and checkpointer setup

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BMOD-03` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-28 complete.

## Allowed outputs

sse/langgraph_runtime.py and focused runtime factory tests.

## Forbidden outputs

Stream-mode or SSE payload changes.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move _process_bindings, _bind_memory_store, _ensure_async_checkpointer, and _compiled_query_graph into one typed factory. Preserve lazy init, lock ownership, Postgres setup prohibitions, process reuse, and fail-closed errors. New module <=280 physical lines.

## Acceptance checks

Runtime factory tests and existing executor compile tests pass. Behavior unchanged.

## Negative tests

Calling checkpointer setup() or losing process reuse fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if the pinned LangGraph checkpointer API cannot be verified from the installed version.

## Required evidence

Append `P08-29` (`BMOD-03`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
