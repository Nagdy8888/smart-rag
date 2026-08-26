---
name: implement-rag-frontend
description: Implements the authenticated Next.js RAG testing frontend, including Stitch design integration, uploads, chat streaming, citations, graph inspection, tables, tools, roles, and safe rendering. Use for frontend or UX implementation.
---

# Implement the RAG Frontend

Read the active Phase 6, 7, or 8 wrapper, its phase shared contract, exactly one selected packet, the linked canonical `shared/frontend/stitch-nextjs-contract.md` when named, and the approved Stitch brief/design before editing UI code. Do not load sibling packets.

Phase 6 first delivers a thin developer UI for sign-in, upload/status including BM25 projection, chat streaming/resume, route and BM25 index/recheck/degradation diagnostics, original/rewritten query, and canonical citations. Integrate Stitch only after this core loop is testable; fall back to an accessible hand-built UI if the timeboxed Stitch output is unusable.

## Contract-first workflow

1. Inspect generated OpenAPI/types and existing route/component conventions.
2. Map each screen action and state to an implemented API contract; do not invent endpoints or response fields.
3. Build reusable design tokens/components while preserving approved Stitch behavior and accessibility.
4. Keep server state in TanStack Query and auth/session handling in `@supabase/ssr`.
5. Implement authenticated fetch SSE with idempotency, ordered event application, heartbeat, reconnect/resume, cancellation, and one terminal state.
6. Render requested/effective route, correction/fallback, graph readiness/backlog ETA/cost, citations, inference chains, table provenance, and usage honestly.
7. Treat model/retrieved content as hostile text. Sanitize approved rich content and never use raw HTML rendering.
8. Request authorized short-lived source URLs on demand; do not expose privileged credentials or internal trace data.

## Required states

Cover first load, loading, empty, success, partial, permission denied, pending URL approval, data-category attestation/review, stale scan/quarantine, graph unavailable/ineligible/backlog, rate-limit degraded, budget limit, upload/ingestion progress, malformed file, stream reconnect, cancellation, conversation deletion, anomaly alert, and server error.

## Verification

- Typecheck, lint, component tests, production build, and Playwright.
- Test keyboard-only operation, focus, screen-reader labels, responsive layouts, and WCAG AA contrast.
- Include XSS payloads in filenames, snippets, entity labels, citations, tool metadata, table cells, and answer markdown.
- Confirm frontend role hiding is convenience only and server denial still occurs for forged requests.
