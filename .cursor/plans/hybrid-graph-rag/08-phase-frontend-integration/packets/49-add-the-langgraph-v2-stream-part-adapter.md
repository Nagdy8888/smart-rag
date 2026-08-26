---
phase: 8
packet: 49
status: pending
title: "Add the LangGraph v2 stream-part adapter"
requirement_ids: [P08-49]
---

# Packet 49 — Add the LangGraph v2 stream-part adapter

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BEP-02` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-48 catalog exists. Pinned LangGraph is 1.2.11. Production executor is not switched yet.

## Allowed outputs

sse/stream_parts.py, unit tests, and tests/contract/test_langgraph_stream_v2.py. chunks.py may become a small facade.

## Forbidden outputs

Switching production astream in this packet.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Parse v2 {type, ns, data}, v1 multi-mode tuples, and legacy raw mappings. Unknown modes return None. Contract test builds a real StateGraph, uses get_stream_writer(), and streams updates+custom v2.

## Acceptance checks

Observed installed-version shape/order is asserted. Unit parse tests pass.

## Negative tests

Guessing an unknown shape as updates fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

If the pinned runtime shape differs, update the contract from observed data before producers change.

## Required evidence

Append `P08-49` (`BEP-02`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
