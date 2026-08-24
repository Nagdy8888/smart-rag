---
phase: 8
packet: 10
status: pending
title: "Harden the frontend chat protocol and recovery state"
requirement_ids: [P08-10]
---

# Packet 10 — Harden the frontend chat protocol and recovery state

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-09 verified-final SSE contract is implemented. Current chat-app remains in place.

## Allowed outputs

Typed cancel/feedback, sessionStorage pointer, resume, readiness gating, empty-completion failure, usage labeling.

## Forbidden outputs

Moving chat-app.tsx in this packet. Fake typewriter UI. Storing tokens or retrieved evidence in sessionStorage.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-10 — Harden the frontend chat protocol and recovery state

Purpose: make the existing frontend client accurately represent readiness, admission, progress/final-answer delivery, cancel, feedback, refresh/resume, and safe failures before visual restructuring.

Primary files:

- [`apps/frontend/src/lib/api.ts`](apps/frontend/src/lib/api.ts)
- [`apps/frontend/src/lib/types.ts`](apps/frontend/src/lib/types.ts)
- [`apps/frontend/src/lib/chat-view.ts`](apps/frontend/src/lib/chat-view.ts)
- [`apps/frontend/src/lib/sse-consume.ts`](apps/frontend/src/lib/sse-consume.ts)
- [`apps/frontend/src/lib/stream-reconnect.ts`](apps/frontend/src/lib/stream-reconnect.ts)
- current [`apps/frontend/src/components/chat-app.tsx`](apps/frontend/src/components/chat-app.tsx); do not move it in this packet. P08-15 owns the one move to `components/chat/chat-app.tsx`.
- related focused tests and contract docs.

Implementation:

- Add exact types and client support for existing `GET /runs/{run_id}` and `GET /conversations/{conversation_id}` where needed for reload/resume validation. Do not invent transcript fields.
- Change mutation helpers such as cancel and feedback from ambiguous booleans to typed success payloads or classified thrown errors. Callers must not show success when HTTP failed.
- Store only `{conversationId, runId, lastSequence}` for the active run in `sessionStorage`; never store access tokens, retrieved evidence, or full answer/source text there.
- On page reload, fetch the owned run, resume from the durable sequence if running, and clear the pointer when terminal/deleted/foreign. Never submit a second message during recovery.
- Treat `completed` without answer/refusal content as a protocol failure and render a visible safe error.
- Make a terminal SSE `error` visible in the main workspace with safe code and run ID; the collapsed details panel is supplementary.
- Gate paid send on compatible handshake and core `query_ready`. Show the specific safe reason. Do not reserve while the core executor/checkpointer is unavailable.
- Preserve approved Hybrid fallback when only BM25 or graph is degraded; do not block all chat for optional degradation.
- Fix caller usage labeling from “Company total” to “Your usage.” Company usage appears only on the owner/admin Usage tab.
- Keep idempotency keys stable across a failed network retry of the same draft/run and rotate only after a durable terminal.
- Make reconnect state explicit: attempt count, next retry, Cancel, and manual Retry after the bounded automatic ceiling. Retain partial output.

Acceptance tests:

- Cancel success and failure are both visible and correctly classified.
- Feedback shows recorded only after 201; 403/404/422 show failure and preserve the form.
- Refresh during a run resumes without duplicate POST, tokens, or cost.
- Readiness unavailable disables Send with an accessible reason; graph-only degradation still permits approved Hybrid behavior.
- Empty completion is a test failure.
- 402, role/permission 403, 404, 409, 422, 426, 429 with `Retry-After`, and 503 each render approved generic/safe copy.

## Acceptance checks

Cancel/feedback classify HTTP failure. Reload resumes without duplicate POST. Empty completed is a protocol failure. 402/403/404/409/422/426/429/503 copy is approved.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if GET run/conversation contracts needed for resume do not exist; do not invent transcript fields.

## Required evidence

Append `P08-10` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
