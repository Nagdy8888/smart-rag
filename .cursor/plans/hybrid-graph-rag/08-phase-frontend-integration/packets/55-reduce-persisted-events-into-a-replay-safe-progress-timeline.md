---
phase: 8
packet: 55
status: pending
title: "Reduce persisted events into a replay-safe progress timeline"
requirement_ids: [P08-55]
---

# Packet 55 — Reduce persisted events into a replay-safe progress timeline

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `FEP-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45, P08-48, and P08-54 complete.

## Allowed outputs

lib/run-progress.ts, chat-view.ts updates, types/sse.ts wire union only, and tests.

## Forbidden outputs

A second frame reducer. Client timestamps/durations. Accepting token_delta before verificationCompleted.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Own RunProgressState in ChatViewState. applySseFrame remains the only entry. Ignore sequences <= lastSequence. Open/close node and tool items. Legacy status without phase is completed. optional_tool_disclosure never creates an executed-tool row. Protocol terminal freezes new progress additions.

## Acceptance checks

Reducer tests cover start/complete/fail, replay, skipped absent, early token fail-closed, token after verify appends immediately, first terminal wins.

## Negative tests

Rendering or appending an early token fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if applySseFrame would be replaced.

## Required evidence

Append `P08-55` (`FEP-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
