---
phase: 8
status: active
title: Phase 8 shared contracts
---

# Phase 8 shared contracts

Use this file with the [Phase 8 wrapper](../08-phase-frontend-integration.md), exactly one packet in this directory, and the single [Stitch/Next.js contract](../shared/frontend/stitch-nextjs-contract.md).

## Implementation-consumer boundary

Phase 8 consumes the Phase 7-approved [`STITCH_BRIEF.md`](../../../../docs/frontend/STITCH_BRIEF.md), [`API_UI_MAPPING.md`](../../../../docs/frontend/API_UI_MAPPING.md), localization/token decisions, accepted delivered references or explicit component-system fallback, and unresolved-gap record. If any input is absent, return the work to Phase 7; do not rerun design generation or invent contracts.

Implement against real Phase 2/6 Auth/API/SSE contracts. Preserve server-enforced authorization, idempotency, sequence/reconnect, durable budgets, canonical evidence, limitation, and safe-degradation behavior. Production output contains no mocks, placeholders, fake success, client-only permission boundary, or skipped integration proof.

## Delivered Stitch template (not product layout)

The user-delivered Stitch bundle is a **template, not a layout**. Phase 8
must not add Stitch frames as routes, pages, or information architecture,
and must not create placeholder screens for missing Stitch numbers 02, 08,
11, 12, or 13.

Do not copy HTML, demo data, random outcomes, inline scripts, dead links,
client-only permission logic, Combined/Hybrid send chrome, mock diagnostics,
budget editors, audit/PII tabs, or design-system/gallery pages.

Screen list is [`STITCH_REVIEW.md`](../../../../docs/frontend/STITCH_REVIEW.md)
plus [`API_UI_MAPPING.md`](../../../../docs/frontend/API_UI_MAPPING.md): ship
typed-contract surfaces with native UI; do not add Unavailable-gap pages.

Auth-direct sign-up and reset/callback remain in scope because those Auth
APIs exist. MFA enroll/challenge remain historically implemented by packets
1-6 and are scheduled for complete removal in P08-11 and P08-12 after the
user-approved security reduction. Do not claim MFA is gone until both
packets pass.
Record mapping/gap proof in
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../docs/development/phase-08-frontend-integration-evidence.md).

## Token reconciliation

Before implementation, the Phase 7 review must reconcile machine-readable palette/radius definitions in `smart_rag/DESIGN.md`, its prose guidance, and raw Tailwind values in generated frames. `STITCH_BRIEF.md` records canonical tokens. Do not silently choose among conflicting blue, slate, radius, or elevation values, and do not copy the chat gallery blur treatment when the design guide prohibits blur.

## Prohibited production patterns

Production must not ship runtime Tailwind CDN loading, inline event handlers or application scripts, `innerHTML` mutation, `dangerouslySetInnerHTML` for retrieved content, mock or randomized authentication, placeholder `href="#"` navigation, hard-coded third-party avatar URLs, hard-coded diagnostics presented as live data, external font/icon dependencies that violate CSP, demo data, random outcomes, dead links, static authorization, unescaped retrieved markup, or test-auth bypass.

Use build-time Tailwind, typed event handlers and API/SSE data, real Supabase SSR Auth, safe text rendering, real routes, approved asset hosting, CSP-compatible fonts/icons, and server-enforced permissions.

## Ordered packet discipline and evidence

Complete packets `P08-01` through `P08-06` in order. One model run selects exactly one unchecked packet, quotes its exact title, states acceptance checks, and records proof before any checkbox can be checked.

Append packet proof to the Phase 8 evidence document. Include mapping/gap traceability (not Stitch frame numbers), token decisions, real contract mappings, authorization/failure/idempotency/fallback/bounded-resource proof, exact commands/results, unverified external checks, deviations/ADR approval, rollback notes, and handoff blockers. Stop under the wrapper's listed conditions, and do not set phase status complete until its final done gate is proven and accepted.

## Approved remediation amendments (P08-07)

- Packets `P08-07` through `P08-23` are additive remediation after completed `P08-01` through `P08-06`. Do not uncheck historical packets.
- Complete MFA/TOTP/AAL2 removal is an approved planned security reduction recorded in `docs/adr/ADR-frontend-functional-overhaul.md`. It is not implemented until both P08-11 and P08-12 evidence pass. Compensating controls (JWT, revocation, live role/authorization-version, RLS, server owner/admin enforcement, rate limits, destructive confirmations, generic errors, audit, IDOR-safe 404) remain mandatory.
- P08-09 is a Phase 6/Phase 8 co-owned defect repair. It must keep Phase 6 admission, budget, deadline, cancellation, one-terminal, ownership, idempotency, and resume tests green and update both phase evidence records.
- Answer delivery is verified-final, not fake token streaming. Keep LangGraph `stream_mode="updates"`. Hold structured answer text until verification completes, then emit persisted `token_delta` compatibility chunks of at most 4096 characters without typewriter delay.
- Frontend visual packets read [00-visual-contract.md](./00-visual-contract.md) plus their selected packet. Do not search for a new theme.
- Ordered packet discipline now includes `P08-07` through `P08-23` after the original six completed packets.
