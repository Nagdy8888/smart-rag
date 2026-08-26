---
phase: 8
packet: 68
status: pending
title: "Split admin request builders"
requirement_ids: [P08-68]
---

# Packet 68 — Split admin request builders

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-14` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-64 complete.

## Allowed outputs

lib/admin-bodies/{invitations-tools,glossary,entity-rules}.ts and a <=100-line admin-bodies.ts barrel.

## Forbidden outputs

Changing extra-forbid request shapes or concurrency fields.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move builders verbatim. Expand admin-bodies.test.ts for every builder.

## Acceptance checks

Barrel <=100. Builder tests cover every exported function.

## Negative tests

A dropped concurrency field fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if an undocumented builder is found mid-move; inventory first.

## Required evidence

Append `P08-68` (`MOD-14`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
