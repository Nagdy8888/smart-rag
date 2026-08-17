---
phase: 8
packet: 6
status: complete
title: "Run complete Playwright journeys for roles, routing/limitation families, reconnect, API/deploy versioning, fallbacks, table provenance, curation, and graph evidence. Add stable visual/interaction regression coverage keyed to each delivered frame surface, plus explicit journeys for delivered gallery states and required Stitch gaps including MFA recovery, API skew, BM25 degradation, rate limits, Graph Pending/ACL blindness, RTL citations, and restricted evidence audit."
requirement_ids: [P08-06]
---

# Packet 6 — Run complete Playwright journeys for roles, routing/limitation families, reconnect, API/deploy versioning, fallbacks, table provenance, curation, and graph evidence. Add stable visual/interaction regression coverage keyed to each delivered frame surface, plus explicit journeys for delivered gallery states and required Stitch gaps including MFA recovery, API skew, BM25 degradation, rate limits, Graph Pending/ACL blindness, RTL citations, and restricted evidence audit.

Read the [Phase 8 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- `P08-01` through `P08-05` are implemented and narrowly verified.
- Stable authorized fixtures cover roles, routes, failures, limitations, bidi content, version skew, graph/table provenance, and restricted audit.
- Repository-defined build, type, lint, component, accessibility, security, and Playwright commands are known.

## Allowed outputs

- Frontend test/fixture/configuration changes, bounded defect repairs, documentation, and final Phase 8 evidence.
- Stable visual/interaction baselines for accepted frames and approved gap fills.

## Forbidden outputs

- Mock-only success, skipped required journeys, hidden flaky failures, broadened backend redesign, or unchecked external claims.
- Snapshot approval that masks accessibility, authorization, state, data, or contract defects.
- Checking packets, changing phase status, or advancing phases before the final gate is proven and accepted.

## Ordered actions

1. Run production build, strict types, lint, component tests, accessibility checks, security/header/XSS checks, and prohibited-pattern scans.
2. Run Auth/roles/MFA recovery, invitations/owner setup, disabled/revoked sessions, upload permission, quota/expiry/crawl/quarantine, and deletion journeys.
3. Run direct, current-relationship, historical-relationship, broad/global, full-summary pass/refusal, negation, media, comparison, table, Composite, route-correction, deadline/partial, and manual-diagnostic journeys.
4. Run BM25 projection/outage, LightRAG fallback, graph mapping/inspection, `Graph Pending`, authorized ACL blindness with unauthorized silence, table provenance, curation, rate/budget, private-run ownership, and restricted audit journeys.
5. Run startup handshake, old/new deploy skew, minimum-client blocking before paid work, unknown additive SSE events, idempotent submit, heartbeat, cancellation, and sequenced reconnect.
6. Run responsive LTR/RTL, mixed-direction citation/inference/highlight, keyboard/focus/live-region/reduced-motion, and WCAG AA journeys.
7. Compare visual/interaction behavior for design system, sign-in, owner setup, chat/gallery, table, document library/upload/detail, graph explorer, usage/budgets, and every approved missing-frame gap.

## Acceptance checks

- Every wrapper final-gate journey passes with real contracts and stable evidence.
- Per-frame traceability proves approved visual/interaction parity; every missing surface has an approved primitive-based regression.
- Authorization negatives, unauthorized silence, canonical citation/inference links, deterministic table provenance, limitation honesty, and reconnect/idempotency hold.
- No mock data, test-auth bypass, prohibited generated pattern, raw retrieved HTML, or unescaped markup ships.
- Exact commands, versions, timings, failures, bounded repairs, and unresolved managed/external checks are recorded.

## Negative tests

- Forge roles/run/source/document/graph/tool access; downgrade ACL/current version; revoke sessions; replay submissions; reorder/drop events; and kill BM25/LightRAG paths.
- Exercise incompatible clients, unknown events, network loss, rate/budget exhaustion, expired/oversize quarantine, uncovered summaries, unproved negation, media-only evidence, and hostile markup.
- Run RTL/mobile/keyboard/screen-reader/reduced-motion cases and restricted evidence audit with unauthorized actors.
- Fail the gate on skipped, flaky, mock-only, snapshot-only, or non-reproducible required coverage.

## Stop routes

- Stop on any launch-blocking build, type, lint, accessibility, security, authorization, provenance, compatibility, frame/gap, or Playwright failure after bounded repair.
- Report unavailable real integrations or managed checks as unverified; never replace them with fake proof.

## Required evidence

Append `P08-06` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): exact commands/results, per-frame/gap matrix, all journey outcomes, authorization/failure/idempotency/fallback/provenance evidence, prohibited-pattern scan, measured behavior, bounded repairs, unverified external checks, deviations/rollback, and Phase 9 handoff blockers.
