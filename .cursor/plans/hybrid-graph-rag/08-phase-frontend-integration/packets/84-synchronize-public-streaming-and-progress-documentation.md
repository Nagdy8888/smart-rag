---
phase: 8
packet: 84
status: pending
title: "Synchronize public streaming and progress documentation"
requirement_ids: [P08-84]
---

# Packet 84 — Synchronize public streaming and progress documentation

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `DOC-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

Related implementation packets through P08-82 have landed or this packet updates only the landed subset and lists the rest as pending.

## Allowed outputs

workspace-screens, PHASE8_JOURNEY_MATRIX, action-inventory, docs/api SSE, Phase 6/8 evidence, ADR links, docs/README if a new doc was added, and required Mermaid diagrams.

## Forbidden outputs

Copying stale test counts. Documenting unimplemented cache diagnostics as shipped.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Document waiting timeline, verified-display labels, skip/reduced-motion, history behavior, status.phase, tool_progress, ordering, replay, omitted security fields, and local-vs-hosted proof. Sequence, state, and ownership diagrams.

## Acceptance checks

Repository docs checker passes. Commands, paths, and examples match the repository.

## Negative tests

A diagram that still shows updates-only streaming as the only mode after BEP-06 fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a public field is not in the catalog.

## Required evidence

Append `P08-84` (`DOC-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
