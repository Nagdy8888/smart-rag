---
phase: 8
packet: 43
status: pending
title: "Extract citation drawer and chat query ownership"
requirement_ids: [P08-43]
---

# Packet 43 — Extract citation drawer and chat query ownership

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-04` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-42 complete. chat-app.tsx still owns run lifecycle.

## Allowed outputs

citation-drawer.tsx, hooks/use-chat-queries.ts, and focused tests.

## Forbidden outputs

ReadableStream, AbortController, SSE frames, or reconnect timers in the query hook.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move CitationDrawer presentation and /meta /me readiness conversations messages usage citations queries into owners. chat-app.tsx must shrink. Use inspected auth wrapper types.

## Acceptance checks

Render behavior unchanged. Hook owns no stream transport. chat-app.tsx is smaller.

## Negative tests

Query hook importing consumeSse fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if characterization tests fail; revert the extraction.

## Required evidence

Append `P08-43` (`MOD-04`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
