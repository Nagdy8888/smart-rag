---
phase: 8
packet: 80
status: pending
title: "Split chat CSS by extracted owner"
requirement_ids: [P08-80]
---

# Packet 80 — Split chat CSS by extracted owner

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-15` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45 and P08-58 complete.

## Allowed outputs

chat-rail, chat-transcript, chat-composer, and progress/reveal CSS modules.

## Forbidden outputs

Selector duplication, geometry change, or snapshot updates in this move-only packet.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Each module <=280 physical lines. Import from the owning components only.

## Acceptance checks

chat.module.css has no remaining concern over 300 lines. Visual tests unchanged.

## Negative tests

A snapshot update to hide a move fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if FEP presentation classes are still owned by ChatApp.

## Required evidence

Append `P08-80` (`MOD-15`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
