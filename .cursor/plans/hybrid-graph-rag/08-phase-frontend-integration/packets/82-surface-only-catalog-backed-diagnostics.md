---
phase: 8
packet: 82
status: pending
title: "Surface only catalog-backed diagnostics"
requirement_ids: [P08-82]
---

# Packet 82 — Surface only catalog-backed diagnostics

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `CTR-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-52 mapping owners exist.

## Allowed outputs

mapping/diagnostics.py, catalog additions that have authoritative sources, and frontend unknown/absent rendering.

## Forbidden outputs

Inventing cache events. Evidence/source/passage text. Counting deadline as a second terminal.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Map optional_tool_disclosure from optional_selected_keys; route_correction only when applied; coverage from bounded branch coverage_score; deadline.route_family from authorized runtime context before partial. cache deferred.

## Acceptance checks

Positive, absent, malformed, replay, leakage, and deadline-then-partial tests pass.

## Negative tests

Rendering cache miss when no event exists fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a field's runtime source cannot be found.

## Required evidence

Append `P08-82` (`CTR-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
