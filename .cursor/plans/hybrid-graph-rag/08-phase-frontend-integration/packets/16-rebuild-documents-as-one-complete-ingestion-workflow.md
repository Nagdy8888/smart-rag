---
phase: 8
packet: 16
status: pending
title: "Rebuild Documents as one complete ingestion workflow"
requirement_ids: [P08-16]
---

# Packet 16 — Rebuild Documents as one complete ingestion workflow

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-14 shell exists. Move document-library.tsx and document-detail.tsx once.

## Allowed outputs

List/table, created_at frontend type fix, keyset pagination, unified status, upload/crawl/retry/delete, gap-panel removal.

## Forbidden outputs

Backend schema/router edits for created_at. Inventing next_cursor. Source preview/download. Simulated percentages.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-16 — Rebuild Documents as one complete ingestion workflow

Purpose: make document ingestion, status, pagination, and deletion understandable and fully backed by existing APIs.

Primary files:

- move current `apps/frontend/src/components/document-library.tsx` and `document-detail.tsx` once under `apps/frontend/src/components/documents/`
- update every import/test and delete the old source paths in this packet
- [`apps/frontend/src/lib/api.ts`](apps/frontend/src/lib/api.ts), [`apps/frontend/src/lib/types.ts`](apps/frontend/src/lib/types.ts), query keys, tests, docs, and inventory.

Implementation:

- Present one responsive enterprise list/table with title, visibility, status, timestamp, and contextual actions; use cards only at narrow widths.
- Fix only the frontend `DocumentResponse` TypeScript type to include the existing FastAPI `created_at` response field. Do not change the backend schema/router for this item.
- Implement bounded keyset pagination using the real `created_at,id` cursor. Determine continuation with the documented page-size strategy; never invent `next_cursor`.
- Label local filtering as filtering loaded rows, or send only supported server parameters.
- Consolidate `IngestionInspector` and `ProcessingTimeline` into one status component.
- File upload remains reserve → Supabase Storage JWT upload → finalize with one stable idempotency key. Show truthful stages and bytes, never simulated percentages.
- Website crawl remains owner/admin only and preserves one retry key.
- Show Retry only when `retry_allowed` is true.
- Wire existing `DELETE /documents/{document_id}` behind a name-bearing confirmation; handle 204/403/404/rate limit, invalidate list/detail, and navigate safely.
- Remove `DOCUMENT_DELETE_UNAVAILABLE`, source-preview/download UI, and all unsupported GAP panels.
- Link supported document context to Graph/Tables without exposing storage paths, service-role URLs, unauthorized counts, or source text.

Acceptance tests:

- Upload happy path, quota/capability denial, upload/finalize failures, duplicate-click idempotency, and invalidation.
- Crawl success, 403, validation, stable-key retry, and rate limit.
- Delete 204, member 403, foreign 404, second 404, and safe navigation.
- Cursor pagination appends without duplicate IDs and stops correctly.
- Polling stops at terminal/unmount; document context preconfigures only accessible Graph/Tables state.


## Copied visual specification

### Documents page component specification

#### Page layout

- PageHeader title “Documents.”
- Description: “Upload files or add approved websites, then track search and graph readiness.”
- Primary action: “Import source.”
- Toolbar below: loaded-row filter left and count/status summary right.
- Main content is one white bordered DataTable, not multiple dashboard cards.

#### Document table

- Desktop columns: Name, Visibility, Search status, Graph status, Created, Actions.
- Name is the detail Link with document icon; optional ID appears below in monospace only when title is missing.
- Status values come from real document/version status.
- Row overflow menu includes “View details” and owner/admin “Delete.”
- Clicking blank row space does not navigate; only explicit Name link does.
- Mobile card order: Name, two status pills, visibility/created metadata, then overflow.

#### Documents empty state

- Title: “No documents yet.”
- Body: “Import a file or approved website to create searchable company knowledge.”
- Primary “Import source.”

#### `ImportSourceSheet`

- Right drawer width 560px.
- Header “Import source.”
- Two Tabs: “Files” and “Website.” Both map to real APIs.
- File tab: drop zone, selected queue, category Select, attestation Checkbox, Upload button.
- Website tab: URL Input, approved domain Input, optional title, bounded depth/pages controls only if current API exposes them, attestation, “Add website.”
- Keep one stable idempotency key while the same form submission retries.
- On success, close only after showing created document/job IDs or navigate to detail.

#### Upload queue row

- Filename, bytes, stage StatusPill, and Remove before reservation.
- Real stages: “Ready,” “Reserving,” “Uploading,” “Finalizing,” “Queued,” “Failed.”
- Upload byte progress may use a progress bar only if browser/API provides real uploaded bytes.
- Parsing, embedding, BM25, and graph stages use statuses, never fake percent.

#### `IngestionStatus`

- One component used in list/detail.
- Vertical timeline on detail; compact pills on list.
- Ordered labels from real lifecycle: Uploaded, Scanning, Parsing, Search ready, Graph pending/ready/ineligible, Failed, Deletion pending.
- Expandable technical details show scan signature status, OCR, chunks/tables, BM25, queue age, graph handoff, and retry only when fields exist.
- Retry is a real Secondary button visible only when `retry_allowed`.

#### Document detail

- Header: back Link, document title, visibility/status pills, overflow menu.
- Main desktop grid: `minmax(0, 2fr) minmax(280px, 1fr)`.
- Left: processing timeline and real table references.
- Right: metadata definition list and actions to “Inspect in graph” and “Open tables.”
- Delete is in overflow/danger zone, not a large primary button.
- No source preview, download, audit, PII, or raw storage section.

#### Delete confirmation

- Title: “Delete document?”
- Body: `“<safe title>” will be removed from retrieval and scheduled for cleanup. This cannot be undone.`
- Buttons: “Cancel” and Danger “Delete document.”
- Success navigates to Documents and announces “Document deleted.”

## Acceptance checks

Upload/crawl/delete/pagination/polling tests pass. Frontend DocumentResponse includes existing FastAPI created_at.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if DELETE /documents/{id} is absent; do not invent it. Wire only the existing contract.

## Required evidence

Append `P08-16` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
