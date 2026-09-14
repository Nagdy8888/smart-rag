---
title: ADR — Local AnyDoc parser bake-off (no Firecrawl upload)
owner: engineering-lead
status: accepted
last-reviewed: 2026-09-10
audience: engineering, security, reviewers
---

# ADR: Local AnyDoc parser bake-off (no Firecrawl upload)

## Context

The production Hybrid ingest path parses PDFs with PyMuPDF and local Tesseract
inside the no-network parser sandbox (`parser_v1`). Firecrawl AnyDoc 0.2.4 can
convert the same PDF to Markdown locally. Hosted AnyDoc OCR (`ocr=hosted`)
uploads the **entire** PDF to Firecrawl Parse, which is a new subprocessor, is
usage-billed, and does not include Zero Data Retention on free/self-serve
plans.

This experiment compares the current sandbox parser with **local** AnyDoc on
one sealed book PDF without changing production parser selection.

## Decision

1. **Experiment only.** AnyDoc is not registered in the production adapter
   registry, `ParserService`, index graph, or worker defaults.
2. **Two paths only:** `current` (PyMuPDF + local Tesseract) and
   `anydoc_local` (`firecrawl-anydoc==0.2.4`, `ocr="reject"`).
3. **No Firecrawl network.** The AnyDoc sandbox runs `--network none` with
   `ocr=reject`. `FIRECRAWL_API_KEY` is never mounted. `HostedError` or any
   outbound Parse call is a failed experiment, not a fallback.
4. **No fabricated PDF locators.** AnyDoc 0.2.4 PDF success is Markdown only.
   Downstream elements keep `MarkdownLocator`. Missing page/bbox provenance is
   scored as unavailable, never synthesized.
5. **Isolation by document/version IDs** on the existing hosted stack: one
   restricted, graph-ineligible document/version per lane; retrieval uses
   `restrict_version_id`; cleanup deletes only manifest-listed UUIDs.
6. **OpenAI stays on the existing gateway.** Embeddings, rerank, answers, and
   the PDF judge use `SharedSettings.openai_api_key`. The key is never copied
   into the parser sandbox or child-process command lines.
7. **Experiment-only host Vision OCR.** After named/date owner approval on
   2026-09-10, the AnyDoc lane may raster AnyDoc-named pages and pages with no
   selectable text and transcribe them with `gpt-4o-mini` (`store=False`, no
   Files API, no `wrap_openai`). This is transcription OCR, not figure
   captioning, and is not a production `ParserService` path. Firecrawl Parse
   remains forbidden.
8. **Single-document scope.** The first report must set
   `generalization_claim=false`. A primary-parser replacement requires later
   multi-PDF qualification and an ADR that changes production defaults.

## Consequences

- Local AnyDoc remains a candidate preprocessor, not a production PDF parser,
  while physical-page citations are required.
- Hosted Firecrawl OCR is out of scope until a separate subprocessor ADR and
  Zero Data Retention decision exist.
- When AnyDoc names pages (`NeedsOcrError.pages`) or a page has no selectable
  text, the bake-off OCRs those pages on the host with OpenAI Vision and
  splices Markdown in original page order. AnyDoc-safe runs stay in the
  no-network sandbox. That is not Firecrawl Parse. An all-scanned PDF still
  fails closed if the page cap is exceeded or any OCR call fails.

## Related

- [ADR-parser-isolation.md](./ADR-parser-isolation.md)
- [PARSER_BAKEOFF.md](../evaluation/PARSER_BAKEOFF.md)
- [PARSER_SANDBOX.md](../ingestion/PARSER_SANDBOX.md)
- [PDF_HYBRID_EVALUATION.md](../evaluation/PDF_HYBRID_EVALUATION.md)
- [OPENAI_DATA_GOVERNANCE.md](../security/OPENAI_DATA_GOVERNANCE.md)
- [SUBPROCESSOR_GOVERNANCE.md](../security/SUBPROCESSOR_GOVERNANCE.md)

## Approval

| Role | Name | Date |
| --- | --- | --- |
| Engineering lead | user (Cursor chat; bake-off mandate) | 2026-09-09 |
| Product owner | user (Cursor chat; OpenAI Vision OCR of bake-off pages) | 2026-09-10 |
