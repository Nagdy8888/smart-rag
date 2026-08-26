---
phase: 8
packet: 83
status: pending
title: "Remove the framework disclosure header and document HSTS ownership"
requirement_ids: [P08-83]
---

# Packet 83 — Remove the framework disclosure header and document HSTS ownership

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `SEC-03` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-24 complete. Deployed HTTPS edge must be identified from repository docs, not guessed.

## Allowed outputs

next.config.ts poweredByHeader false, deployment/security doc ownership notes, and production-profile header assertions.

## Forbidden outputs

Contradictory HSTS from Next and the edge. Preload unless irreversible prerequisites are proven.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Disable X-Powered-By. Identify the real HTTPS terminator. Record one HSTS owner. If the edge cannot be identified, ship only poweredByHeader false and mark HSTS BLOCKED.

## Acceptance checks

X-Powered-By absent from the production build response. Exactly one documented HSTS owner or an explicit BLOCKED HSTS note.

## Negative tests

Guessing CloudFront and Vercel both own HSTS fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop without inventing an edge owner.

## Required evidence

Append `P08-83` (`SEC-03`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
