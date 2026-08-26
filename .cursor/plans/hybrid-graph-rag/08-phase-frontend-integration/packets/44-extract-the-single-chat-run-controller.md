---
phase: 8
packet: 44
status: pending
title: "Extract the single chat-run controller"
requirement_ids: [P08-44]
---

# Packet 44 — Extract the single chat-run controller

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-05` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-43 complete.

## Allowed outputs

hooks/use-chat-run.ts, its test, and optional lib/paid-run-pointer.ts if the hook would exceed 300 lines.

## Forbidden outputs

A second SSE parser or byte/frame parser inside the hook. Changing terminal/replay/idempotency semantics.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move send lock, idempotency, paid-run pointer, AbortController, resume, reconnect timers, cancel, ChatViewState publication, and latest refs. Only this hook calls startOrResumeMessageStream, resumeEventStream, and consumeSse.

## Acceptance checks

Hook <=300 lines. Tests cover send, sync POST, interrupt, resume, non-OK resume, deleted run, cancel, sign-out, switch, double-click, and unmount.

## Negative tests

ChatApp calling consumeSse after this packet fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if behavior tests fail; revert before another extraction.

## Required evidence

Append `P08-44` (`MOD-05`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
