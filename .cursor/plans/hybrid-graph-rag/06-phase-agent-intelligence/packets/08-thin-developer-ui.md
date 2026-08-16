---
phase: 6
packet: 8
status: pending
title: "Ship the thin authenticated developer UI and prove route, fallback, injection, idempotency, budget, outage, event-loop, and privacy gates."
requirement_ids: [P06-08]
---

# Packet 8 — Ship the thin authenticated developer UI and prove route, fallback, injection, idempotency, budget, outage, event-loop, and privacy gates.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

## Preconditions

- Packets 1–7 are accepted with evidence; no UI fixture may substitute for their real authorization, retrieval, graph, table, budget, SSE, checkpoint, governance, or deletion boundaries.
- Existing frontend package/design conventions, test commands, browser-direct Supabase Auth contract, API versions, and signed user-visible limitation language are inspected rather than invented.
- This packet delivers only the thin developer UI. Phase 7 exclusively owns the five-business-day/two-revision Stitch review and component-library fallback decision; Phase 8 owns production UI integration.

## Allowed outputs

- A minimal authenticated developer UI for sign-in, upload/status, chat streaming/reconnect/cancel, route/BM25/cache/coverage/limitation diagnostics, citations, and feedback, plus focused component/E2E/integration/evaluation evidence.
- Small shared frontend types/clients/tests/docs required to consume the accepted additive API/SSE contract safely.

## Forbidden outputs

- Stitch generation/review, production design system, full production frontend, Phase 8 feature breadth, managed deployment/CDN proof, hidden admin data, manual production routing, unsafe HTML, or client-side authorization assumptions.
- Mock-only claims for route quality, one-paid-run behavior, budget/crash recovery, outages, event-loop gates, conversation deletion, or canonical citations.

## Ordered actions

1. Implement browser-direct Phase 2-qualified Supabase sign-in and use the resulting Bearer JWT for FastAPI; display explicit upgrade/auth/session-revoked states without treating UI state as authorization.
2. Provide source upload and status views for the accepted lifecycle, including Hybrid/Graph readiness and visible failure/retry states, without claiming graph readiness from upload alone.
3. Implement version handshake and fetch-based POST SSE. Preserve one client-generated message idempotency key across retry, store the latest sequence, resume with `after={sequence}`, tolerate/log unknown additive events, expose cancel, and never restart paid work on reconnect.
4. Render safe streaming stage/token/completion/deadline/partial/sanitized-error events. Show requested/effective/corrected route, fallback/limitation reason, BM25 availability/index/lag/recheck/degradation, graph mode/survival/readiness/authorized blindness, cache/recheck, coverage/section gaps, optional tools, usage, and deadline state.
5. Render canonical citations that open exact authorized file page/section/sheet/slide/URL coordinates; render deterministic table provenance and ordered atomic-link inference citations. Never display BM25 snippets, native graph prose, raw source HTML, or unauthorized counts.
6. Provide explicit signed UI behavior for `temporal_graph_limitation`, whole-document uncovered sections, negation scope/refusal, media limitation, insufficient evidence, graph fallback, and deleted/unavailable citations.
7. Capture thumbs/correction feedback through packet 7's distinct tags and expose the feedback handle without leaking private prompt/trace payloads.
8. Prove every route and mixed case through the thin UI: direct/current relationship/multi-hop/historical/broad-global/whole-document/negation/media/comparison/table/inspection/no-retrieval/multi-part/Composite, manual mode only on diagnostic controls, one correction, and safe deadline/refusal.
9. Prove fallback/outage behavior: killed/incompatible ParadeDB visibly yields dense+term Hybrid with no snippet/stale evidence; LightRAG loss/survival failure visibly relabels Combined→Hybrid; Valkey endpoint policies fail closed or visibly degrade only approved reads; cache delete/ACL downgrade yields zero stale evidence.
10. Prove one-paid-run behavior across double click, retry, disconnect, process restart, replay expiry boundaries, and cancel; display budget/usage without enabling the client to choose or enlarge reservations.
11. Run prompt/BM25-query/graph/tool/citation-forgery/PDF/HTML/OCR/entity/relation/XSS payloads through UI/API boundaries and prove structured isolation, encoding, schema rejection, and citations only from supplied canonical IDs.
12. At five simultaneous Composite UI streams, verify route deadlines/ceilings, p95 event-loop lag below 50 ms, heartbeat jitter below two seconds, and no missed 15-second heartbeat; a miss blocks release or triggers an independent query-runner design.
13. Delete a conversation from the UI and immediately prove all read/history/resume/citation paths deny it and no application/checkpoint/store/private-feedback/event state remains; show only content-free deletion acknowledgment.
14. Run packet 7's disjoint evaluations and integrated E2E gates, map every wrapper `Deliver`, `Review`, and `Done when` clause to exact evidence, record unavailable Phase 9/10 managed checks as blockers, and request explicit user acceptance without checking the packet prematurely.

## Acceptance checks

- The thin UI proves authenticated sign-in, upload/status, safe stream/reconnect/cancel, route/BM25/limitation diagnostics, exact citations/table/inference links, and early feedback; it contains no Stitch or production-frontend scope.
- Complete route, historical/coverage/negation/media/ACL-blindness, correction, fusion/union, table, verifier, fallback, injection, cache, idempotency, reservation, provider/FastAPI rate, reaper, additive API/SSE, outage, audit, governance, and privacy cases pass through real local boundaries.
- ParadeDB failure visibly degrades to dense+term with zero stale/unauthorized/BM25-snippet evidence; graph failure never becomes graph-only prose; every route ends within 25/45/30/50/10-second deadlines, `recursion_limit=24`, one correction, and its call/tool ceilings.
- Double send/reconnect/restart/expiry creates one paid run; all gateway calls consume one durable reservation without overspend; endpoint-specific Valkey loss and cache recheck remain observable and safe.
- Five Composite streams meet p95 event-loop lag `<50 ms`, heartbeat jitter `<2 s`, and zero missed 15-second heartbeats.
- Conversation deletion leaves no scoped application/checkpoint/store/private-feedback/event/citation state, and traces/feedback/UI output remain redacted, versioned, governed, and XSS-safe.
- The wrapper's unchanged final Deliver/Review/Done gate has a one-to-one evidence map; status remains pending until every item is proven and the user accepts it.

## Negative tests

- Client role/route/budget override, stale JWT, unauthorized diagnostic/count/citation, production manual mode, duplicate paid click/reconnect, missing sequence, unknown event crash, raw HTML/XSS, forged citation, BM25 snippet, graph prose answer, unsupported limitation bypass, stale cache hit, Valkey mutation fail-open, missed heartbeat, event-loop block, unbounded branch/tool/model call, partial conversation deletion, raw trace/secret, mock-only gate, Stitch/Phase 8 scope, or managed proof claim fails.

## Stop routes

- Stop if any prior packet lacks accepted evidence, the thin UI requires weakening protocol/security/accessibility contracts, a real local boundary cannot prove a launch-blocking gate, or any wrapper Done item fails after bounded repair.
- Do not mark complete, start Stitch, implement Phase 8, run lock update, or claim Phase 9/10 managed evidence.

## Required evidence

- Append to [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md): UI routes/screens and safe-rendering tests, auth/upload/status traces, SSE handshake/sequence/reconnect/cancel captures, diagnostic/citation/table/inference payloads, full route/fallback/outage/injection/idempotency/budget/cache/reaper/privacy E2E results, five-stream event-loop/heartbeat metrics, evaluation hashes/reports, exact commands/exit codes, wrapper gate matrix, managed blockers, deviations/rollback, and explicit user acceptance.
