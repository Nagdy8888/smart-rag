---
phase: 6
packet: 61
status: pending
title: "Repair term and BM25 candidate generation and selectively enrich indexed search terms."
requirement_ids: [P06-61]
---

# Packet 61 — Repair term and BM25 candidate generation and selectively enrich indexed search terms.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-hybrid-retrieval`](../../../../../.cursor/skills/implement-hybrid-retrieval/SKILL.md),
[`implement-ingestion-pipeline`](../../../../../.cursor/skills/implement-ingestion-pipeline/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-60 source-aware ranking is recorded. Branch is
  `fix/general-rag-retrieval-accuracy`.
- Inspect term retrieval, `retrieve_term_candidates`, BM25 query
  construction, and
  [`contextual.py`](../../../../../packages/core/src/smart_rag_core/ingestion/embeddings/contextual.py)
  before editing.
- Verify the pinned ParadeDB/`pg_search` and Supabase RPC contracts
  from current primary docs before adding SQL.

## Allowed outputs

- Term extraction and Hybrid term-channel adapters
- Additive ACL-safe `app.retrieve_term_candidates` expansion that
  remains current-version and ACL rechecked
- BM25 variant/field balancing so one variant cannot consume the
  candidate cap
- Bounded acronym/definition and mixed-case search-term enrichment in
  `contextual.py` only where a needle-in-index audit proves a parse or
  index gap
- Reindex instructions for a single canonical test version
- Synthetic injection, Arabic/mixed, duplicate, stale-version, and
  outage tests
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Sample-PDF-specific aliases, hashes, titles, or gold phrases in
  production extractors, prompts, or tests.
- Reindexing every live duplicate copy.
- Weakening ACL/current-version recheck on term or BM25 survivors.
- Mutating frozen `hybrid_default_v1` bytes in place.
- Starting Packet 62 rerank-accounting or long-document pin work.

## Ordered actions

1. Extract bounded codes, acronyms, entities, and approved aliases
   from the ranking query and feed them to the term channel in
   addition to the remaining sentence.
2. Keep the RPC additive and ACL-safe. Batch-recheck every term ID
   through the authoritative Supabase path.
3. Balance BM25 variants and fields so one variant cannot consume the
   candidate cap.
4. Run a needle-in-index audit on synthetic and existing development
   indexes. Enrich deterministic search terms only for proven
   parse/index gaps (bounded acronym/definition and mixed-case
   tokens).
5. Reindex a single canonical test version after enrichment. Do not
   delete other copies.
6. Add synthetic injection, Arabic/mixed, duplicate, stale-version,
   and BM25/term outage tests.

## Acceptance checks

- Term channel receives bounded extracted tokens, not only the whole
  sentence.
- ACL-denied, stale, and deleted chunks never survive term or BM25
  recheck.
- One BM25 variant cannot fill the entire candidate cap.
- Enrichment is generic and digest-tested; committed tests have no
  sample-PDF literals.
- Outage path records `bm25_unavailable` or `term_unavailable` and
  degrades without fake success.

## Negative tests

- SQL injection through extracted terms fails closed.
- Unauthorized glossary aliases must not leak into another principal's
  results.
- Reindexing all live copies in this packet fails.
- Adding sample-PDF gold as an approved alias fails.

## Stop routes

- Stop if the additive RPC cannot stay `app_api` plus RLS/ACL safe.
- Stop if enrichment would require document-specific gold phrases.
- Do not pin a long-document profile here.

## Required evidence

- Packet file under `docs/development/phase-06/` plus index append.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_term_candidates.py tests/unit/test_bm25_variant_balance.py tests/unit/test_search_term_enrichment.py -q
  uv run python scripts/check.py --tier docs
  git diff --check
  ```
