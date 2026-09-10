---
phase: 6
packet: 23
status: complete
title: "Implement conservative PDF heading extraction for structure-aware chunking."
requirement_ids: [P06-23]
---

# Packet 23 — Implement conservative PDF heading extraction for structure-aware chunking.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-ingestion-pipeline`](../../../../../.cursor/skills/implement-ingestion-pipeline/SKILL.md).

## Preconditions

- Pinned `pymupdf==1.25.5` is inspectable. Verify current primary docs before
  coding. Packet 19 overlay is recorded.

## Allowed outputs

- Additive edits to `packages/core/src/smart_rag_core/ingestion/parser/adapters/pdf_adapter.py`
  and helpers/types required for heading classification
- Parser policy version bump if required
- Fixtures and unit tests
- Count-only docs updates in chunking/evaluation docs

## Forbidden outputs

- Reusing old chunk IDs or labels.
- Hardcoding this PDF’s title, fonts, or source text.
- Weakening the 200–400 token band or 600-token cap.
- Enabling Graph for the private PDF.
- Live ingest in this packet if operator gates are missing; record the
  blocker instead.

## Ordered actions

1. Confirm PyMuPDF 1.25.5 structured text dictionary keys from current docs.
2. Keep `get_text("text")` for scanned-page detection and repeated-line
   cleaning.
3. Classify short standalone large/bold blocks as headings; leave uncertain
   body text as paragraphs.
4. Preserve reading order, bbox, page labels, OCR fallback, and
   deterministic element IDs for the new parser version.
5. Prove headings populate `section_path` through chunking.
6. Re-ingest only as a new Graph-disabled version when operator gates exist.

## Acceptance checks

- Large/bold short titles become headings. Bold body sentences do not.
- Repeated headers are removed, not promoted.
- Arabic/mixed text and scanned fallback remain intact.
- Encrypted/over-limit PDFs still fail closed.

## Negative tests

- Sentence-like bold paragraphs remain `PARAGRAPH`.
- Existing page-label tests still pass.

## Stop routes

- Stop if the pinned PyMuPDF API cannot be verified from current docs.
- Do not mutate existing ingested versions.

## Required evidence

- Append unit command/exit, heading-count metrics when measured, and
  Packet 24 handoff. Live reingest remains operator-owned when blocked.
