---
phase: 8
packet: 54
status: pending
title: "Prove route-aware progress, replay, and leakage bounds"
requirement_ids: [P08-54]
---

# Packet 54 — Prove route-aware progress, replay, and leakage bounds

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BEP-07` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-53 complete. Scope-graph route fixtures exist.

## Allowed outputs

tests/unit/test_query_sse_route_progress.py, tests/contract/test_sse_progress_replay.py, and checked-in public SSE fixtures needed by later FEP/VER work.

## Forbidden outputs

Hard-coded company pipelines for general/mixed/invalid routes.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Assert one start and at most one terminal status per executed node. Explicit required/forbidden stage sets per route. Tools only when selected/executed. First token_delta after verify. Serialized events exclude query/secret/draft/evidence/tool args/results/exception text. Monotonic sequences. Legacy status without phase replays. One protocol terminal.

## Acceptance checks

Route, replay, resume, and leakage tests pass. Public fixture is checked in.

## Negative tests

A skipped node appearing in a general fixture fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Do not start FEP packets until this packet passes.

## Required evidence

Append `P08-54` (`BEP-07`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
