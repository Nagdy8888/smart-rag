---
phase: 8
packet: 47
status: pending
title: "Classify resume failures and abort stale reconnect work"
requirement_ids: [P08-47]
---

# Packet 47 — Classify resume failures and abort stale reconnect work

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `COR-04` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-44 use-chat-run exists.

## Allowed outputs

use-chat-run.ts, sse-consume.ts, stream-reconnect.ts, and their tests.

## Forbidden outputs

Generic SSE timeout, swallowing non-OK in consumeSse, or starting a second paid run.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Preserve deleted-run 404. Classify every other non-OK resume through the API error classifier. Stop retry on revoked/unauthorized/forbidden. Read lastSequence/run/terminal/failure from refs. Abort and clear timers on cleanup/switch/sign-out/unmount. Keep resume cursor monotonic.

## Acceptance checks

401/403: one safe failure, no retry loop. 500: bounded retry then action. 404: existing deleted UX. Unmount/switch abort. Duplicate sequence ignored. Terminal: no reconnect.

## Negative tests

Parsing a 401 body as SSE fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if resume would restart paid work.

## Required evidence

Append `P08-47` (`COR-04`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
