---
name: stitch-nextjs-contract
status: active
section: 12
owners: [phase-07-specification, phase-08-implementation]
---

# 12. Stitch brief and Next.js frontend

This is the single canonical Section 12 contract. Phase wrappers, phase shared contracts, and packets link here and do not reproduce this body.

## Ownership and phase boundary

- **Phase 7 owns specification:** create and review [`docs/frontend/STITCH_BRIEF.md`](../../../../../docs/frontend/STITCH_BRIEF.md) and [`docs/frontend/API_UI_MAPPING.md`](../../../../../docs/frontend/API_UI_MAPPING.md), run the bounded design review, reconcile localization and design-token decisions, record unresolved contract gaps, and obtain approval or select the component-system fallback.
- **Phase 8 owns implementation consumption:** verify and consume the approved Phase 7 documents, accepted delivered references or explicit fallback, localization/token decisions, and gap record. Implement them against real Phase 2/6 contracts without restarting design generation, porting generated HTML verbatim, replacing backend authorization with client guards, or preserving mock data.
- The Phase 7 paragraphs that describe production integration and tests are binding specification inputs for Phase 8; they do not authorize production frontend implementation in Phase 7.
- Phase 8 returns an API/Auth/SSE contract gap to its owning phase instead of inventing an endpoint, field, state, or success path.

## Required Phase 7 specification outputs

Before frontend implementation, Phase 7 creates the two linked frontend documents. `STITCH_BRIEF.md` contains copy-ready prompts, responsive LTR/RTL frames, information hierarchy, component inventory, copy and limitation messaging, localization and canonical-token decisions, accessibility requirements, and every required loading, empty, error, permission, quarantine, quota, compatibility, limitation, fallback, partial-readiness, budget, and degraded state. `API_UI_MAPPING.md` maps every visible field, action, and state to a verified typed Phase 2/6 Auth/API/SSE contract and records unresolved gaps without mock behavior.

The approved brief, mapping, localization/token reconciliation, accepted frame references or fallback decision, and unresolved-gap record are required Phase 8 inputs. Bundle presence alone does not complete Phase 7, and Phase 8 does not recreate these artifacts.

## Required screens and visible contracts

The specification and implementation cover:

- Sign in, sign up, Google OAuth, forgot/reset password, auth callback, MFA enrollment/challenge, and the Phase 2-audited lost-factor recovery, identity reverification, session revocation, and re-enrollment procedure. Include disabled/revoked-session handling and a clear `MFA required for upload` permission state.
- Initial owner setup, invitation acceptance, and team member/role management.
- Main chat defaulting to `Auto`. An advanced test panel offers `Hybrid`, `Combined`, `Structured table`, and `Graph inspection`, explains route semantics, and displays original/rewritten query; profile language, temporal, negation, document-scope, media, and historical fields with confidence; per-channel candidate counts; BM25 index/projection/recheck/degraded status; rerank decision/fallback; cache hit/recheck; section coverage and uncovered ranges; coverage/refusal/limitation reason; correction/deadline state; partial graph readiness; authorized ACL graph blindness; inference chains with atomic citations; source drawer; feedback; and token/latency/cost diagnostics.
- Distinct, non-alarming chat states for BM25-unavailable dense+term degradation, the figure/chart v1 limitation, historical-relationship Hybrid routing, authorized ACL graph blindness, full-summary scoped refusal, and negation clarification.
- Document library with category/processing attestation; file upload and used/remaining quota; pending, abandoned, expired, and oversize quarantine; pending URL-source admin approval; scan engine/signature status; quarantine/review; crawler destination provenance; ingestion/parser/OCR/media-only status; BM25 projection and Hybrid readiness; graph backlog/rolling ETA/cost; retry; version; anomaly alerts; and deletion.
- Document detail with source/chunk preview, graph entities/relationships, restricted-preview auditing, and review states.
- Graph explorer with search, bounded neighborhood visualization, path evidence, source links, and distinct `Graph Pending` versus authorized ACL-restricted-not-indexed notices. Notices reveal no unauthorized count, title, or source detail.
- Structured-table results with deterministic execution separated from generated analysis and with formula, exact cell provenance, sortable results, and authorized export behavior.
- Tool catalog/admin with compact cards, full manifest drawer, permissions, version, enable state, and usage; retrieval curation for Hybrid aliases and graph canonical type/alias/do-not-merge rules; and categorized feedback approval.
- Usage, budgets, graph-maintenance reserve/degradation, rate-limit feedback, audit history including restricted evidence/preview/download events for authorized owner/admin users, profile, and company settings.
- Startup/API compatibility states for handshake failure, a blocking client-below-minimum upgrade message before paid submission, version switchover, and forward-compatible handling of unknown additive SSE events without breaking an active answer.

## State and API mapping requirements

- Every visible action, field, transition, diagnostic, role gate, and error maps to an implemented typed Auth/API/SSE contract. The map identifies owner, request/event/response field, authorization boundary, loading/terminal behavior, idempotency/reconnect behavior, and failure/fallback state.
- Real server authorization remains authoritative. UI hiding is convenience only; forged requests must still be denied.
- Streaming uses the Phase 6 Bearer-authenticated POST and persisted sequence contract, with idempotent submission, schema/version handshake before paid work, heartbeats, ordered additive events, cancellation, reconnect/resume, one terminal state, and safe handling of unknown additive events.
- Diagnostic labels and values come from typed live contracts. Generated frame copy, static values, random outcomes, or HTML are not API definitions.
- Loading, empty, partial, refusal, permission, MFA, quota, quarantine, compatibility, deadline, cancellation, reconnect, fallback, degraded-service, and generic production-error behavior is explicit for each applicable surface.
- Limitation and fallback states remain honest: graph-only is inspection; BM25 outage degrades visibly to dense+term; LightRAG failure falls back to Hybrid; historical relationships route to Hybrid with the temporal limitation; media-only claims, unproved negation complements, and uncovered full summaries refuse or guide as specified; ACL graph blindness discloses nothing unauthorized.

## Arabic, bidirectional, responsive, and accessibility contract

Before design generation, `STITCH_BRIEF.md` records whether v1 localizes application chrome into Arabic or retains English chrome with Arabic content support. Either choice supports `dir="rtl"` layouts where applicable and `dir="auto"` plus safe bidi isolation for user messages, evidence, entity names, citations, codes, URLs, and source snippets.

Concrete reviewed fixtures and screen examples cover mixed Arabic/English text, LTR codes/URLs inside RTL paragraphs, punctuation, logical citation/highlight offsets tied to canonical text rather than visual order, line height and diacritics, IME/caret behavior, responsive overflow, desktop/mobile breakpoints, keyboard navigation, directional focus order, focus/error states, live regions, and reduced motion.

The design and implementation meet WCAG AA contrast, keyboard-only operation, accessible names and status announcements, safe responsive layouts, and equivalent LTR/RTL task completion. Missing RTL or mobile Stitch frames are missing design evidence to fill and review, not a waiver.

## Bounded Stitch review and fallback

Phase 6's thin developer UI for sign-in, upload/status, chat streaming/reconnect, route/BM25 diagnostics, and citations is a prerequisite. Timebox the user-run Stitch generation/review loop to five business days and two revision rounds. If no implementable accessible export is approved, document the decision and proceed in Phase 8 with the chosen accessible component primitives and canonical design tokens rather than blocking backend validation.

## Phase 8 implementation contract

Integrate the approved Stitch output or fallback into [`apps/frontend/`](../../../../../apps/frontend/) using Next.js App Router, TypeScript strict mode, build-time Tailwind/design tokens, accessible primitives, `@supabase/ssr`, TanStack Query for server state, and a typed streaming client. Preserve approved visual intent and frame traceability while replacing mock data, static diagnostics, demo JavaScript, external placeholder assets, and insecure client-only guards with real API/Auth boundaries.

Render every document, entity, relation, tool, filename, citation, table cell, and retrieved/model string as text with framework escaping. Retrieved content may not use `dangerouslySetInnerHTML`. Apply CSP/security headers, approved CSP-compatible fonts/icons/assets, generic production errors, and no production test-auth bypass.

Implement responsive desktop/mobile and the approved localization behavior, including Arabic-primary RTL layouts, safe mixed-direction content, logical citation/highlight offsets, keyboard/focus/live-region/reduced-motion behavior, WCAG AA contrast, and all required error, permission, compatibility, limitation, partial, fallback, and degraded states.

## Phase 8 verification contract

Production build, strict types, lint, component tests, accessibility checks, security tests, and Playwright must cover:

- sign-in/up, Google OAuth, reset/callback, invitations, owner setup, roles, disabled/revoked sessions, MFA enrollment/challenge/recovery/re-enrollment, and upload permission;
- upload quota/expiry/crawl, attestation, quarantine, scan, parse/OCR/media-only, BM25 projection, Hybrid/Graph readiness, backlog, retry, version, anomaly, and deletion;
- direct, current-relationship, historical-relationship, broad/global, full-summary pass or refusal, negation, media, comparison, table, and Composite routing;
- BM25 projection/outage degradation, LightRAG fallback, deadlines/partial results, rate limits, budget states, route correction, diagnostics, feedback, citations, atomic inference links, and private run ownership;
- startup/API handshake, client/API deploy skew, version switchover, additive unknown SSE events, idempotent submission, sequenced reconnect, heartbeat, and cancellation;
- graph inspection, mapping evidence, `Graph Pending`, authorized ACL blindness with unauthorized silence, table provenance, curation, restricted evidence audit, and server-enforced administration permissions;
- responsive desktop/mobile LTR/RTL, mixed-direction citations/inferences/highlights, keyboard/focus/live-region/reduced-motion behavior, WCAG AA contrast, CSP/security headers, strict escaping, and XSS fixtures.

Tests and production output contain no mock data, fake success, skipped integration proof, test-auth bypass, raw retrieved HTML, or unescaped retrieved markup.
