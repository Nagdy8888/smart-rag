---
phase: 8
packet: 42
status: pending
title: "Split API domain modules into an exports-only barrel"
requirement_ids: [P08-42]
---

# Packet 42 — Split API domain modules into an exports-only barrel

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-03` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-41 complete.

## Allowed outputs

lib/api/{readiness,chat,sse,documents,graph,tables,usage,invitations,tools,knowledge}.ts and a <=100-line api.ts barrel.

## Forbidden outputs

Retries on paid POST, hidden auth refresh, or SSE parsing in the API layer.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Extract one domain at a time. Preserve endpoint, method, body, header, timeout, status, and parser behavior. Keep stream bodies unconsumed in api/sse.ts. Explicit exports only.

## Acceptance checks

api.ts is exports-only and <=100 lines. Each domain <=300. Lint, typecheck, and api tests pass.

## Negative tests

SSE frame parsing inside api/sse.ts fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a domain exceeds 300; split that domain instead of compressing.

## Required evidence

Append `P08-42` (`MOD-03`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
