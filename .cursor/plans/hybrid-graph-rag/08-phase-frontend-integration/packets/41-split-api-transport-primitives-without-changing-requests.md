---
phase: 8
packet: 41
status: pending
title: "Split API transport primitives without changing requests"
requirement_ids: [P08-41]
---

# Packet 41 — Split API transport primitives without changing requests

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-02` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-40 complete.

## Allowed outputs

lib/api/{errors,http,headers,parsers}.ts and re-exports from api.ts.

## Forbidden outputs

Fetch URL/header/status changes. Domain modules importing the api.ts barrel.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move failure unions, apiUrl, bounded JSON, throwIfNotOk, paid/resume/admin headers, and shared parsers verbatim. Keep ApiAuth in one primitive owner.

## Acceptance checks

api.test.ts and prohibited-pattern tests pass. Each primitive module <=280.

## Negative tests

A changed timeout or sanitized-detail precedence fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a primitive would need a new network behavior to compile.

## Required evidence

Append `P08-41` (`MOD-02`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
