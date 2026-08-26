---
phase: 8
packet: 75
status: pending
title: "Render truthful loading, error, and empty states"
requirement_ids: [P08-75]
---

# Packet 75 — Render truthful loading, error, and empty states

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `UX-02` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45 complete.

## Allowed outputs

tables-app.tsx and its tests first. Additional surfaces only if no extra behavior change is required; otherwise stop and do not broaden.

## Forbidden outputs

Empty success copy while pending or forbidden.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

pending without cache -> labelled loading; error -> safe banner + retry; success [] -> domain empty; success data -> content; background refetch keeps content.

## Acceptance checks

Tables tests cover unresolved promise, 403, 500, empty array, cached refetch, and success. Error and empty copy are mutually exclusive.

## Negative tests

No structured tables while the first query is pending fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop rather than editing documents/graph/admin if they need a separate behavior packet.

## Required evidence

Append `P08-75` (`UX-02`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
