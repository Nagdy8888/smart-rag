---
phase: 8
packet: 61
status: pending
title: "Split AnalysisPlan presentation into focused sections"
requirement_ids: [P08-61]
---

# Packet 61 — Split AnalysisPlan presentation into focused sections

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-08` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-60 complete.

## Allowed outputs

components/tables/analysis-plan/* section components. Parent keeps patchDraft and Analyze submission.

## Forbidden outputs

Fetch or compile inside child sections.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Reduce analysis-plan.tsx to <=200 lines. Children <=220. Preserve keyboard labels for add/remove/reorder.

## Acceptance checks

Existing table tests pass. Parent remains the compile owner.

## Negative tests

A child fetching analysis results fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if visual behavior changes unintentionally.

## Required evidence

Append `P08-61` (`MOD-08`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
