---
phase: 6
packet: 6
status: pending
title: "Implement versioned additive API/SSE contracts, compatibility handshake, resumable fetch SSE with persisted sequence IDs, heartbeats, cancellation, reconnect, sanitized errors, and deadline/partial events."
requirement_ids: [P06-06]
---

# Packet 6 — Implement versioned additive API/SSE contracts, compatibility handshake, resumable fetch SSE with persisted sequence IDs, heartbeats, cancellation, reconnect, sanitized errors, and deadline/partial events.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

## Preconditions

- Packets 1–5 are accepted; packet 1 supplies authorized idempotent runs and packet 5 supplies thin chat/compatibility routers, endpoint authorization, local proxy configuration, and event-loop instrumentation.
- Durable run-event schema/sequence allocation, conversation/run ownership, cancellation, deadlines, and sanitized diagnostic contracts exist and can be tested through disconnect/restart.
- Phase 6 proves application protocol, local proxy/configuration, compatibility, concurrency, and tests. Phase 10 owns managed CloudFront/WAF/Caddy IaC, independent Vercel/API skew, origin restrictions, and a deliberately slow run through the real staging CDN.

## Allowed outputs

- Versioned additive OpenAPI/SSE schemas, `/api/meta` handshake, Bearer-authenticated fetch SSE submission/resume, persisted event sequencing, heartbeat/cancel/reconnect/deadline/partial/error behavior, local proxy timeout/buffering configuration contract, clients/fixtures/tests/docs/evidence.
- Additive persistence/API changes strictly needed for event sequence/replay and compatibility.

## Forbidden outputs

- WebSocket transport for v1, cookie-only unauthenticated stream, paid work before compatibility failure, destructive/renamed/repurposed fields within a major version, ephemeral-only events, unowned resume/history, duplicate paid work after reconnect, unsanitized exceptions/source text, or managed-CDN success claims.
- Implementing packet 7 retention reaping, packet 8 production UI, CloudFront/WAF/KMS/S3 infrastructure, origin restrictions, or fake 50-second staging proof.

## Ordered actions

1. Publish `api_version`, `sse_schema_version`, and `min_client_version` through `/api/meta` or the documented equivalent. Require clients to send their version and return an explicit upgrade response before reservation/paid work when below minimum.
2. Use fetch-based SSE from a Bearer-authenticated POST, not WebSocket. Every message carries the packet 1 client-generated user/conversation/idempotency key; duplicate sends return the existing authorized run.
3. Persist every stream event with one monotonically increasing run-local sequence/event ID before delivery. Initial submission may stream immediately; authorized `GET /runs/{run_id}/events?after={sequence}` replays only later events after disconnect.
4. Verify user ownership on submit, fetch, resume, cancel, history, and citation access, except explicit owner/admin audited authorization. Tombstoned conversations and unauthorized/deleted runs deny immediately.
5. Evolve OpenAPI and SSE additively within a major version: never remove, rename, or repurpose an existing field/event. Put `sse_schema_version` in the first event; clients ignore and log unknown additive event types.
6. Emit safe events for stage/status, heartbeat every 15 seconds, monotonic ID, route correction, limitation, deadline/partial status, cache/coverage diagnostics, optional-tool disclosure, citation preview, token delta, usage, completion, cancellation, and sanitized errors.
7. Propagate disconnect/cancel/deadline to bounded graph/model/tool/pool work while preserving already-paid usage and durable terminal reconciliation. A reconnect resumes persisted events and never restarts paid execution.
8. Disable buffering for local Caddy/proxy streaming. Define configuration inputs asserting Caddy upstream/read timeout, CloudFront `OriginReadTimeout`, and CloudFront `OriginKeepaliveTimeout` are each 90 seconds—above the 50-second maximum run deadline plus margin and within current provider limits—rather than relying on defaults.
9. Prove locally: protocol framing, version handshake, additive schema, unknown-event tolerance, event persistence/order, heartbeat/reconnect/cancel, sanitized terminal errors, deadline/partial events, held-stream concurrency, proxy no-buffering, and timeout configuration contract.
10. Integrate packet 5's five-simultaneous-Composite gate: p95 event-loop lag below 50 ms, heartbeat jitter below two seconds, and no missed 15-second heartbeat. Any miss blocks release or triggers an independent query-runner design.
11. Hand retention to packet 7: completed idempotency keys default to seven days and completed events to 30 days through a dedicated reaper; active/retryable keys survive and conversation deletion purges keys/events immediately.
12. Record Phase 10 blockers for IaC assertions, real staging CDN 50-second stream, Vercel/API deploy skew, buffering/origin behavior, and managed topology; do not claim those checks in Phase 6.

## Acceptance checks

- Incompatible clients fail explicitly before paid work; supported clients receive the first `sse_schema_version` event and tolerate/log unknown additive events.
- Bearer POST submission and authorized `after={sequence}` replay preserve strictly increasing persisted IDs, no gaps/duplicates beyond defined replay semantics, one paid run, and exact resume after disconnect/restart.
- Heartbeats occur every 15 seconds; cancel/reconnect/sanitized error/deadline/partial behavior is durable and authorization-safe.
- Local proxy buffering is disabled and all three timeout inputs are exactly 90 seconds; the 50-second maximum-run configuration has margin without a fake managed proof.
- Five held Composite streams meet p95 event-loop lag `<50 ms`, heartbeat jitter `<2 s`, and zero missed 15-second heartbeats.

## Negative tests

- Below-minimum client, paid work before handshake, removed/renamed/repurposed schema field, unknown event crashing client, missing/duplicate/decreasing sequence, replay from zero/after boundary, foreign run/conversation, tombstoned conversation, disconnect restarting execution, cancellation leak, raw exception/secret/source in event, heartbeat miss, buffering, default/short timeout, process restart, and claimed-but-unrun CDN check fail.

## Stop routes

- Stop if events cannot be durably sequenced before delivery, ownership cannot be enforced on every replay/cancel path, cancellation cannot bound downstream work, additive compatibility cannot be contract-tested, or local held streams miss the event-loop/heartbeat gate.
- Managed proof remains an explicit Phase 10 blocker rather than a Phase 6 workaround.

## Required evidence

- Append to [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md): OpenAPI/SSE schema versions/diffs, handshake timing versus reservation, persisted sequence/replay rows, reconnect/restart/cancel traces, event catalog/sanitization tests, heartbeat/jitter/event-loop metrics, held-stream concurrency, local proxy buffering and 90-second config assertions, retention handoff, explicit Phase 10 blockers, exact commands/exit codes, deviations, rollback, and packet 7 handoff.
