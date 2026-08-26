---
phase: 8
packet: 77
status: pending
title: "Bring drawer, command menu, and menu focus to parity"
requirement_ids: [P08-77]
---

# Packet 77 — Bring drawer, command menu, and menu focus to parity

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `UX-04` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-67 overlay CSS exists. Current primitives are inspected.

## Allowed outputs

ui/focus-trap.ts, ui/body-scroll-lock.ts (<=100 each), and primitive tests. No new UI dependency.

## Forbidden outputs

Positive-tabindex hacks or duplicated trap implementations.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Drawer: backdrop, click-close, body lock, Tab wrap, Escape, focus restore. Command menu: initial focus, trap, lock, restore #shell-command, no shortcut while typing. Menu: first enabled item, wrap arrows, Home/End, restore trigger.

## Acceptance checks

Nested lock, wrap both directions, restore, backdrop, Home/End, and unmount cleanup tests pass.

## Negative tests

Shortcut firing inside an editable field fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if Sheet already meets the contract and Drawer can reuse it without a new dependency.

## Required evidence

Append `P08-77` (`UX-04`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
