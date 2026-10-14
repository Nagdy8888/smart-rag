---
title: ADR — Keep PDF code, tables, and figures native
adr_id: ADR-pdf-native-types
status: accepted
owner: engineering-lead
last-reviewed: 2026-10-14
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-10-14"
audience: engineering, reviewers, security
---

# ADR: Keep PDF code, tables, and figures native

## Status

Accepted on 2026-10-14. The user asked for PDF tables, code, and images to be ingested and retrieved as those types, and chose vision descriptions plus showing the image, and typed table columns plus a rendered table.

## Context

Phase 1 recorded that figure, chart, and diagram pixels are not interpreted. Questions that needed only a figure returned `media_limitation`. The PDF adapter also flattened code and tables into paragraphs, so retrieval could not return a listing, a table, or an image.

## Decision

- Monospace PDF lines become `code` elements with newlines and rebuilt indentation.
- Captioned or page-continued row bands become table header and cell elements. They are stored as one pipe-table passage and as typed Parquet in `table-artifacts`. PyMuPDF `find_tables` is not used.
- Image blocks above 80×80 pixels become figure locators. After promotion, the worker stores a PNG in the private `figure-artifacts` bucket and may call the pinned chat model once per figure to describe only what is visible. The parser sandbox still has no API key. A failed description keeps the image and leaves the description empty.
- A figure question is retrieved. `media_limitation` remains when no stored figure is in the selected evidence. When one is, the answer can include the description and an authorized PNG.
- Parser version is `parser_v1_pdf_reflow_v5`. Chunking policy is `chunking_v3`. Stored PDFs stay on the old text until they are re-ingested. Re-ingest is a separate approved run.

## Consequences

- Chunk ids for re-ingested PDFs change.
- Each kept figure can spend one `gpt-4o-mini` vision call at ingest. The cap is 40 figures per document and 1.5 MiB per PNG.
- Figure bytes are readable only after `caller_can_read_document` succeeds. The answer UI does not accept an image URL from the model.
