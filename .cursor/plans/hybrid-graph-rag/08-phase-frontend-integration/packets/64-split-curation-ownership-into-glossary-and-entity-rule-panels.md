---
phase: 8
packet: 64
status: pending
title: "Split curation ownership into glossary and entity-rule panels"
requirement_ids: [P08-64]
---

# Packet 64 — Split curation ownership into glossary and entity-rule panels

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-10` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-62 complete.

## Allowed outputs

glossary-panel.tsx, entity-rules-panel.tsx, use-curation-mutations.ts. curation-panel.tsx becomes a <=150-line tab shell.

## Forbidden outputs

Dropping stale-row conflict UI or permission gates.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Preserve all seven mutation contracts and scoped invalidations. Panels <=280; hook <=250.

## Acceptance checks

administration-surfaces tests cover 403, concurrency conflict, retry, approve/revoke, and rollback.

## Negative tests

A lost conflict banner fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a mutation contract cannot be found.

## Required evidence

Append `P08-64` (`MOD-10`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
