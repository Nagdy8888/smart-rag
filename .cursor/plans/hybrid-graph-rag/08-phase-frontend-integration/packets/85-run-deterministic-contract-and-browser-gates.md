---
phase: 8
packet: 85
status: pending
title: "Run deterministic contract and browser gates"
requirement_ids: [P08-85]
---

# Packet 85 — Run deterministic contract and browser gates

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `VER-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-25 through P08-84 coding packets that are not hosted-only are implemented.

## Allowed outputs

Checked-in SSE fixtures, sse-progress-fixture.spec.ts, architecture/security/reveal/progress tests, and evidence of actual gate counts.

## Forbidden outputs

Unexpected skips. Screenshot-only timing proof. Reusing the draft 47-file/327-test baseline.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Add company/general/invalid/reconnect/long-answer fixtures. Playwright intercepts the real stream endpoint and asserts progress-before-prose, skipped nodes absent, verify, skip, reduced motion, reconnect, cancel. Run format/lint/types/unit/contract/docs/frontend/openapi/migrations/integrity/git diff --check.

## Acceptance checks

Every applicable root tier passes or is listed FAIL/UNVERIFIED honestly. Architecture budgets are machine-enforced. No unexpected skip.

## Negative tests

A skipped required authenticated-browser job that still reports pass fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop on launch-blocking failures after bounded repair attempts.

## Required evidence

Append `P08-85` (`VER-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
