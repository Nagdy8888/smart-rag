---
phase: 8
packet: 79
status: pending
title: "Isolate load-earlier races and pagination errors"
requirement_ids: [P08-79]
---

# Packet 79 — Isolate load-earlier races and pagination errors

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `UX-06` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45 and P08-59 owners exist.

## Allowed outputs

Conversation action/query hook and scroll hook updates plus tests.

## Forbidden outputs

Writing a page into a newly selected conversation.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Use abort or a monotonic token keyed by conversation ID. Restore scroll only after the matching page commits. Failure preserves messages and shows retry. Stale completion/failure is ignored.

## Acceptance checks

Rapid A-B switch, out-of-order completion, abort, retry, empty final page, and anchor preservation pass.

## Negative tests

Conversation B showing A's older page fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if the pagination API cannot supply a cursor compatible with the token.

## Required evidence

Append `P08-79` (`UX-06`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
