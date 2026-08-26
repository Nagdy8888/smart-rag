---
phase: 8
packet: 59
status: pending
title: "Pin conversation scroll only while the user stays at the bottom"
requirement_ids: [P08-59]
---

# Packet 59 — Pin conversation scroll only while the user stays at the bottom

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `FEP-05` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-58 complete.

## Allowed outputs

hooks/use-conversation-scroll.ts and focused tests.

## Forbidden outputs

Scrolling window, #main, or the session rail.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Pin when distance from bottom <=48px. Wheel/touch/manual upward scroll unpins. Reveal growth scrolls only while pinned. Jump to latest re-pins. Load-earlier restores height-delta anchors. Conversation switch ignores stale pagination.

## Acceptance checks

Tests cover pin, unpin, reveal growth, jump, prepend, switch, and pagination failure.

## Negative tests

Following reveal after the user scrolled up fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if the actual conversation scroller cannot be identified.

## Required evidence

Append `P08-59` (`FEP-05`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
