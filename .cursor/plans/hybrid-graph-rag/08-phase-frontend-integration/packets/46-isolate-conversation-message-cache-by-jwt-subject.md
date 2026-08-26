---
phase: 8
packet: 46
status: pending
title: "Isolate conversation-message cache by JWT subject"
requirement_ids: [P08-46]
---

# Packet 46 — Isolate conversation-message cache by JWT subject

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `COR-03` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-43 query owner exists. query-keys.ts is inspectable.

## Allowed outputs

sessionQueryKeys conversationMessages, chat query/run owners, and focused tests.

## Forbidden outputs

Raw JWT or role in query keys. Calling UI filtering a security boundary.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Key conversation messages with the existing non-secret session scope from JWT sub. On sub change, remove session-owned cache, pagination maps, transcript, live run, and persisted pointer after aborting an in-flight stream. Sign-out still clears private state.

## Acceptance checks

User A cache is gone after token replacement with user B before B fetch resolves. Malformed token scope is isolated. Typecheck passes.

## Negative tests

A title/message/run from A rendering for B fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if server authorization would be replaced by cache filtering.

## Required evidence

Append `P08-46` (`COR-03`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
