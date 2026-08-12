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

## Delivered Stitch visual reference

The delivered bundle is under [`stitch_smart_rag_enterprise_console/`](../../../../stitch_smart_rag_enterprise_console/). Its HTML is a visual and interaction reference, not production code, a route/API contract, an authorization design, or a source of diagnostic field names. Recreate approved behavior with typed React components and real contracts; do not copy demo data, random outcomes, inline scripts, dead links, or client-only permission logic.

Frame-to-surface traceability is:

- [`smart_rag/DESIGN.md`](../../../../stitch_smart_rag_enterprise_console/smart_rag/DESIGN.md) and [`frame_00_design_system/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_00_design_system/code.html): shared tokens and primitives for buttons, status badges, citation chips, inputs, file drop zones, and enterprise tables.
- [`frame_01_sign_in/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_01_sign_in/code.html): transactional sign-in without the authenticated application shell.
- [`frame_03_owner_setup_invitations/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_03_owner_setup_invitations/code.html): invitation summary, initial owner setup, MFA gate, retention choice, draft, and initialization actions.
- [`frame_04_main_chat_auto_routing/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_04_main_chat_auto_routing/code.html): authenticated shell, Auto-first chat, manual route controls, pipeline stepper, inference-chain banner, document-scope chips, citations, streaming state, and diagnostics drawer.
- [`frame_04_chat_state_gallery/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_04_chat_state_gallery/code.html): verified, partial, refusal, contradictory-authority, route-correction, degraded-service, and reconnect patterns. It is a state/component reference and need not become a route.
- [`frame_05_structured_table_result/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_05_structured_table_result/code.html): separate deterministic data-execution and generated-analysis regions with formula, cell provenance, sortable results, and export action.
- [`frame_06_document_library/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_06_document_library/code.html): document filters, readiness columns, row actions, upload/website entry points, and pagination.
- [`frame_07_file_upload_ingestion_flow/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_07_file_upload_ingestion_flow/code.html): file drop, category/processing attestation, per-file scan/parse/failure/readiness progress, and commit action.
- [`frame_09_document_detail_audit/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_09_document_detail_audit/code.html): quarantine review, source/chunk/graph/audit tabs, PII and low-confidence review states, graph mappings, and pipeline metadata.
- [`frame_10_graph_explorer/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_10_graph_explorer/code.html): three-pane graph filters, bounded visualization, selected relationship, canonical evidence, and diagnostic metadata.
- [`frame_14_usage_budgets_dashboard/code.html`](../../../../stitch_smart_rag_enterprise_console/frame_14_usage_budgets_dashboard/code.html): usage metrics, route-cost views, graph-maintenance degradation, budget policies, critical reserve state, and notification controls.

## Required delivered-design gaps

There are no delivered frames numbered 02, 08, 11, 12, or 13. There is no complete visual reference for sign-up, password reset/callback, MFA enrollment/challenge/recovery, upload-MFA denial, team administration, tools, alias/entity curation, profile, company settings, API-version incompatibility, restricted-read/download audit history, rate-limit feedback, BM25-specific diagnostics, `Graph Pending` versus authorized ACL graph blindness, or Arabic/RTL and mixed-direction examples.

These are required gap-fill surfaces, not optional scope. Implement them from the approved mapping, real contracts, localization decision, and canonical frontend contract. Record each gap and its approved reuse of delivered primitives in [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../docs/development/phase-08-frontend-integration-evidence.md).

## Token reconciliation

Before implementation, the Phase 7 review must reconcile machine-readable palette/radius definitions in `smart_rag/DESIGN.md`, its prose guidance, and raw Tailwind values in generated frames. `STITCH_BRIEF.md` records canonical tokens. Do not silently choose among conflicting blue, slate, radius, or elevation values, and do not copy the chat gallery blur treatment when the design guide prohibits blur.

## Prohibited production patterns

Production must not ship runtime Tailwind CDN loading, inline event handlers or application scripts, `innerHTML` mutation, `dangerouslySetInnerHTML` for retrieved content, mock or randomized authentication, placeholder `href="#"` navigation, hard-coded third-party avatar URLs, hard-coded diagnostics presented as live data, external font/icon dependencies that violate CSP, demo data, random outcomes, dead links, static authorization, unescaped retrieved markup, or test-auth bypass.

Use build-time Tailwind, typed event handlers and API/SSE data, real Supabase SSR Auth, safe text rendering, real routes, approved asset hosting, CSP-compatible fonts/icons, and server-enforced permissions.

## Ordered packet discipline and evidence

Complete packets `P08-01` through `P08-06` in order. One model run selects exactly one unchecked packet, quotes its exact title, states acceptance checks, and records proof before any checkbox can be checked.

Append packet proof to the Phase 8 evidence document. Include frame/gap traceability, token decisions, visual/interaction regression results, real contract mappings, authorization/failure/idempotency/fallback/bounded-resource proof, exact commands/results, unverified external checks, deviations/ADR approval, rollback notes, and handoff blockers. Stop under the wrapper's listed conditions, and do not set phase status complete until its final done gate is proven and accepted.
