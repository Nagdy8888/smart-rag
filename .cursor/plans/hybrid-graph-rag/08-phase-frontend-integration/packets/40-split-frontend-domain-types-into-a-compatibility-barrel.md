---
phase: 8
packet: 40
status: pending
title: "Split frontend domain types into a compatibility barrel"
requirement_ids: [P08-40]
---

# Packet 40 — Split frontend domain types into a compatibility barrel

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-24 complete. types.ts exports are inventoried.

## Allowed outputs

apps/frontend/src/lib/types/*.ts and a <=100-line types.ts export barrel.

## Forbidden outputs

Changing event strings, request fields, optionality, or public names.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move auth, readiness, chat, documents, graph, tables, usage, admin-tools, admin-knowledge, and sse contracts verbatim. Domain files must not import the barrel. Add a test of the known event list, not source-layout snapshots.

## Acceptance checks

Barrel <=100 physical lines. Each domain <=220. External imports remain valid. Typecheck and api/sse tests pass.

## Negative tests

A renamed export or circular import fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if an export cannot be moved without a behavior change.

## Required evidence

Append `P08-40` (`MOD-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
