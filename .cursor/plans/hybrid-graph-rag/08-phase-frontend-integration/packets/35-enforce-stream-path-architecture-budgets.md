---
phase: 8
packet: 35
status: pending
title: "Enforce stream-path architecture budgets"
requirement_ids: [P08-35]
---

# Packet 35 — Enforce stream-path architecture budgets

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BMOD-09` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-27 through P08-34 complete.

## Allowed outputs

tests/contract/architecture_scanner.py, test_architecture_budgets.py, and test_stream_architecture_budgets.py.

## Forbidden outputs

Exception entries for files this suite is supposed to shrink. Lowering the repo-wide cap in a way that fails unrelated phases.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Add exact stream-path physical-line targets: graph.py and bound-node modules; executors/support and extracted owners; service/persist and extracted owners; query_sse_mapping.py and sse/mapping/. Facades <=100; runtime owners <=300.

## Acceptance checks

Focused architecture budget tests pass. No undocumented production exception for a shrunk file.

## Negative tests

A god file over budget without an explicit reviewed exception fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a required owner still exceeds budget; extract further instead of hiding lines.

## Required evidence

Append `P08-35` (`BMOD-09`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
