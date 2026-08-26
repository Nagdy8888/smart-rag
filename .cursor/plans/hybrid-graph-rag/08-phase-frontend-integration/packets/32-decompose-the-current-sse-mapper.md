---
phase: 8
packet: 32
status: pending
title: "Decompose the current SSE mapper"
requirement_ids: [P08-32]
---

# Packet 32 — Decompose the current SSE mapper

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BMOD-06` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-24 complete. query_sse_mapping.py is inspectable.

## Allowed outputs

sse/mapping/{status,citations,usage,limitations,contracts,verified,mapper}.py and a <=100-line query_sse_mapping.py facade.

## Forbidden outputs

Adding progress or diagnostic events in this packet.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move mapper behavior verbatim into focused owners. Keep current event order/payloads identical. Each new mapping module <=250 physical lines.

## Acceptance checks

No draft answer text is released. Mapper, verified-final, lifecycle, and protocol tests pass. Facade <=100 lines.

## Negative tests

A changed event order or released draft fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if parity tests fail. Do not add BEP events here.

## Required evidence

Append `P08-32` (`BMOD-06`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
