---
phase: 8
packet: 28
status: pending
title: "Extract executor protocol and fixture"
requirement_ids: [P08-28]
---

# Packet 28 — Extract executor protocol and fixture

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BMOD-02` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-27 complete or independently satisfied. Current executors.py is inspectable.

## Allowed outputs

sse/executor_protocol.py, sse/fixture_executor.py, and compatibility re-exports from executors.py.

## Forbidden outputs

Production stream-mode or settlement behavior changes.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move QueryRunExecutor and FixtureQueryRunExecutor verbatim. Keep re-exports so current imports/tests do not change. Prove fixture start count, hold/cancel, extra event order, and optional terminal.

## Acceptance checks

Existing executor/fixture tests pass. Public import paths remain valid.

## Negative tests

Breaking FixtureQueryRunExecutor start/hold/cancel fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a caller cannot import the previous names from executors.py.

## Required evidence

Append `P08-28` (`BMOD-02`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
