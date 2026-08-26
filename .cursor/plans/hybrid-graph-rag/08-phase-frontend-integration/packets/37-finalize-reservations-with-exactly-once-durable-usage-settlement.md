---
phase: 8
packet: 37
status: pending
title: "Finalize reservations with exactly-once durable usage settlement"
requirement_ids: [P08-37]
---

# Packet 37 — Finalize reservations with exactly-once durable usage settlement

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `P08B-02` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-34 owners exist. P08-36 hosted schema is current or explicitly BLOCKED separately.

## Allowed outputs

Edits in run_settlement.py, event_append.py, answer_persistence.py, and the thin service.py orchestrator plus settlement tests.

## Forbidden outputs

Fake UI usage rows, swallowed settlement errors, or price/budget semantic changes.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Ensure success/refusal/partial/error/cancel finalize the reservation exactly once. Replay cannot insert a second settlement. Persistence failure is observable. Commit order avoids the current deadlock boundary. Usage UI derives from durable outcome.

## Acceptance checks

Settlement/lifecycle/resume tests pass. One bounded hosted run has one terminal and the expected usage row, or hosted proof is BLOCKED.

## Negative tests

Two usage rows for one idempotency key fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if hosted schema functions contradict the repository contract.

## Required evidence

Append `P08-37` (`P08B-02`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
