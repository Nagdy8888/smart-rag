---
phase: 8
packet: 76
status: pending
title: "Fix session-list semantics and confirmable delete"
requirement_ids: [P08-76]
---

# Packet 76 — Fix session-list semantics and confirmable delete

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `UX-03` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45 conversation-action owner exists.

## Allowed outputs

conversation-rail.tsx, CSS, action hook, and chat-app tests.

## Forbidden outputs

A Delete control nested inside role=option.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Use list/listitem with one primary selection control and a sibling overflow/delete menu. ConfirmDialog for delete. Pending disables duplicate confirm. Failure keeps the row. Active delete aborts the run.

## Acceptance checks

No [role=option] button nesting. Keyboard selection, cancel, server failure, double click, and active-session success pass.

## Negative tests

Silent delete failure fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if ConfirmDialog is missing; use the existing primitive.

## Required evidence

Append `P08-76` (`UX-03`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
