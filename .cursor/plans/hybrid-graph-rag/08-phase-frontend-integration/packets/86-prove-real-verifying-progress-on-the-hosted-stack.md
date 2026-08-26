---
phase: 8
packet: 86
status: pending
title: "Prove real Verifying progress on the hosted stack"
requirement_ids: [P08-86]
---

# Packet 86 — Prove real Verifying progress on the hosted stack

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `P08B-04` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-54, P08-56, and P08-85 complete. Hosted stack prerequisites as in P08-26.

## Allowed outputs

Hosted proof evidence and a narrow producer or reducer fix only if the missing layer is identified.

## Forbidden outputs

Minimum display duration, backend sleep, fake timer, or forced React paint. Patching both layers blindly.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Prove event store has status stage=verify_answer phase=started, the browser receives it, the timeline renders Verifying, no prose before verify completion, and completed update precedes the first verified token.

## Acceptance checks

PASS requires stored, received, and rendered verify start. Fast completion may appear only as history but the event remains.

## Negative tests

A client timer labeled Verifying fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

BLOCKED if hosted credentials or provider budget are unavailable.

## Required evidence

Append `P08-86` (`P08B-04`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
