---
phase: 8
packet: 27
status: pending
title: "Extract bound graph-node construction"
requirement_ids: [P08-27]
---

# Packet 27 — Extract bound graph-node construction

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BMOD-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-24 complete. Current graph.py and node modules are inspectable. Move-only; no progress wrappers yet.

## Allowed outputs

apps/agents/src/smart_rag_agents/query/runtime/bound_nodes.py and tests/unit/test_query_node_bindings.py. Topology-only edits to graph.py.

## Forbidden outputs

Progress events, stream-mode changes, or deleting supported node names/routes.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move nested production node callables from build_query_graph into a typed BoundQueryNodes owner. Preserve (state, Runtime[QueryGraphContext]) -> QueryGraphState and deps_from_runtime. graph.py keeps route functions, exact add_node stage names, edges, studio-only nodes, and compile/checkpointer entry.

## Acceptance checks

Registered node names and route paths are equivalent. graph.py <=300 physical lines. New module <=300. Binding and route tests pass.

## Negative tests

Changing a stage name or skipping a studio compile fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if parity tests fail. Do not add progress to make tests pass.

## Required evidence

Append `P08-27` (`BMOD-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
