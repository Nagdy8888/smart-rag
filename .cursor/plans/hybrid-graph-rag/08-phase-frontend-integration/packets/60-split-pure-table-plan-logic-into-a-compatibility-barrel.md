---
phase: 8
packet: 60
status: pending
title: "Split pure table-plan logic into a compatibility barrel"
requirement_ids: [P08-60]
---

# Packet 60 — Split pure table-plan logic into a compatibility barrel

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-07` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45 complete. table-plan.ts is inspectable.

## Allowed outputs

lib/table-plan/{draft,validate,compile,results}.ts and a <=100-line table-plan.ts barrel.

## Forbidden outputs

Accepting previously rejected SQL-like input.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move types/copy, validation, compileTablePlanDraft, and result/export guards verbatim. Update internal imports.

## Acceptance checks

table-plan, tables-app, and api tests pass. Typecheck passes.

## Negative tests

A newly accepted dangerous identifier fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if compile behavior would change.

## Required evidence

Append `P08-60` (`MOD-07`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
