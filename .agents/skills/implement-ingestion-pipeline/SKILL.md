---
name: implement-ingestion-pipeline
description: Implements or changes durable file, OCR, website, table, chunking, embedding, versioning, deletion, and indexing workflows. Use for ingestion workers, parsers, crawlers, queues, and document lifecycle work.
---

# Implement Durable Ingestion

Read the active Phase 3 wrapper and selected inline packet contract plus only its explicitly linked schema/security prerequisites. GraphRAG implementation remains Phase 5-owned; do not load later phases or infer work from legacy section numbers.

## Preserve canonical lifecycle statuses

Expose `Uploading` while direct upload is incomplete, then `Uploaded`, `Scanning`, `Parsing`, `Hybrid Ready`, `Graph Pending`, `Graph Ready`, `Graph Ineligible`, `Deletion Pending`, or `Failed`. Normalizing, chunking, embedding, and graph indexing are internal LangGraph nodes, not new public/database lifecycle enums.

Failure, retry, cancellation, deletion, ACL downgrade, and quarantine are explicit states or durable jobs. Never infer progress from missing rows.

## Implementation checklist

1. Keep polling/claim/lease/heartbeat/reclaim/release in `apps/worker`; invoke the graph with a claimed `job_id`, lease token, and durable Storage reference—not bytes or a worker-local path. The first graph node validates the lease and fetches the exact object through the core Storage gateway; graph nodes remain restartable/idempotent and never claim queue rows.
2. Enforce admission, concurrency, file-size, expanded-size, page/sheet/row, OCR, crawl, and model-budget limits. URL sources require owner/admin approval and use only the dedicated crawl-egress proxy; re-resolve/validate DNS/IP on every redirect and pin/check the actual connection peer IP.
3. Pin/patch the ClamAV engine, update signed databases at least daily with `freshclam`, persist engine/signature versions per scan, reject signatures older than 24 hours, and re-scan before promotion when stale or changed. Frozen signatures are CI-only.
4. Run untrusted parsers/OCR with no network, non-root credentials, constrained resources, and no application secrets. Preserve the shared-kernel risk ADR and its gVisor/Kata/separate-host upgrade triggers.
5. Before any external model call, require uploader category/authority attestation, local deterministic sensitive-pattern checks, and an approved `external_processing_allowed` decision; prohibited/unknown/contradictory content remains quarantined.
6. Preserve source bytes privately and store extracted/chunk/table artifacts as versioned outputs.
7. Emit typed headings, paragraphs, lists/items, tables/rows/cells, code, captions, pages/slides, links, coordinates, and reading order. Apply versioned repeated-header/footer and HTML main-content/boilerplate cleaning while preserving original snapshots and removal diagnostics.
8. Follow `docs/ingestion/CHUNKING_CONTRACT.md`: 200–400 embedding-token prose targets, 40–60 adjacent-prose overlap, 600-token normal hard cap, heading ancestry, row/list-item atomicity, reconstructable oversized-element exceptions, and parent sections capped at 1,500 tokens.
9. Exact-dedup by normalized SHA-256 and near-dedup within a document/site version using the evaluated policy. Require the plan's fuzzy-dedup precision/recall gate or fall back to exact-only. Keep representative plus `duplicate_of_chunk_id` and all source provenance; never hard-delete cross-document variants with different authority/date.
10. Extract XLSX/CSV typed cells to Parquet/table manifests; do not flatten tables into prose only.
11. Populate canonical chunks, parent links, offsets/pages, language, titles/headings, approved SME glossary/search terms, and aliases deterministically.
12. Embed through the pinned shared model gateway with durable per-job/batch reservations, idempotency, tracing, and usage reconciliation.
13. Transactionally enqueue the versioned BM25 projection after canonical vector/term writes. Process it through the project-owned `Bm25Indexer` with leased idempotent jobs, bounded batches, stable canonical IDs, separate ParadeDB writer credentials, row-count/hash verification, sampled candidate checks, and priority ACL/delete cleanup.
14. Mark Hybrid Ready only after structure, dedup, canonical data, vector/term indexes, and the private ParadeDB BM25 projection pass integrity checks. A new version with failed/pending projection is not fully Hybrid Ready.
15. For a graph-eligible Hybrid Ready version, create exactly one durable `Graph Pending` handoff job with canonical version/config identity. Phase 3 does not call LightRAG, build graph maps, or claim Graph Ready.
16. For replacement, build the new canonical vector/term/BM25 data with retrieval visibility off and hand its graph-eligible version to Phase 5; the later verified pointer transaction owns graph visibility and old derived cleanup.
17. For deletion/ACL downgrade, exclude canonical/table retrieval and increment BM25 visibility generation atomically, enqueue high-priority projection and graph-cleanup handoffs, and rely on authoritative resolver rejection while Phase 5 performs graph cleanup.
18. ACL expansion never auto-enables graph indexing; require authorized admin approval for a new graph-index job.

## Tests

Use real small fixtures for each format plus repeated PDF header/footer and multi-page table, nested DOCX lists/tables, PPTX caption/group order, Markdown code/list/table, HTML navigation/cookie/sidebar boilerplate, Arabic mixed direction, oversized atomic elements, exact/near/cross-document duplicates, stale/incompatible malware signatures, prohibited/unknown category, missing URL approval, malformed, encrypted, zip-bomb, OCR, formula, crawl-loop, SSRF/egress bypass, worker-crash, cancellation, re-embedding, replacement, deletion, and ACL-downgrade cases.

Prove no partial version becomes current and no stale BM25 or graph evidence survives authoritative Supabase resolver checks.
