---
name: implement-hybrid-retrieval
description: Implements and evaluates canonical Supabase plus private ParadeDB BM25 hybrid retrieval, including pgvector, exact terms, query variants, RRF, temporal policies, reranking, MMR, parent expansion, and table dispatch. Use for retrieval code, RPCs, BM25 adapters, ranking, and retrieval evaluations.
---

# Implement Hybrid Retrieval

Read the active Phase 4 wrapper and selected inline packet contract before editing. Copy formulas and thresholds from that packet and its frozen evidence into named, typed configuration with comments linking each value to its evaluation.

## Pipeline contract

1. Produce a typed query profile with confidence/provenance per field: language/configuration, intent, entities/approved aliases, exact terms/codes/numbers, filters, temporal intent/date, variants, table intent, relationship signals, and decomposition.
2. Generate bounded variants without changing entities, numbers, negation, date constraints, or requested scope.
3. Retrieve independent channels:
   - private digest-pinned ParadeDB/`pg_search` BM25 over a rebuildable canonical projection, using typed parameterized allow-listed field/phrase/boolean queries, evaluated title/identifier > heading/alias > body boosts, Unicode tokenization, and byte-identical canonical-projection/core-query Arabic normalization while preserving raw citation text;
   - filtered pgvector HNSW with iterative scans and selectivity-aware `ef_search`;
   - deterministic trigram/exact search over populated filenames, titles, codes, glossary terms, and approved aliases.
4. Give `Bm25Retriever` only server-derived opaque authorization scope and allow-listed filters. Batch-recheck every BM25 ID through the authoritative Supabase RPC before fusion; scan at most 300 IDs with one top-300 query (cursor only if a later pin qualifies it) to obtain at most 75 authorized survivors. Never use BM25 snippets as evidence.
5. If ANN under-fills, increase an allow-listed profile once and then use a bounded exact scan only when the authorized subset is admitted at or below 10,000 rows with hard statement/work/row bounds. Planner estimates are an admission hint, not the safety boundary.
6. Fuse by RRF using the maximum contribution across variants per channel/passage, not the sum; raw BM25/vector/trigram scores only order their own lists.
7. Apply only the plan's bounded multiplicative metadata factors.
8. Apply explicit `latest`, `current`, `recent`, and `as_of` policies across documents.
9. Start accuracy-first: retrieve up to 100 dense, 75 authorized BM25 survivors, and 30 term candidates across all variants, fuse, then rerank a top-20 pool for every non-trivial query with at least two authorized candidates. Skip only the plan's fully supported trivial exact lookup; never use raw BM25 or fused-score gaps.
10. Validate that the reranker returns only unique supplied candidate IDs, ranked with bounded support scores. Unknown/duplicate IDs, malformed output, timeout, cancellation, or budget failure falls back to deterministic RRF with a recorded reason.
11. After reranking, apply query-class-calibrated MMR/quotas, parent expansion, context budget, duplicate-cluster handling, and citation provenance.
12. Compute `HybridCoverage`; permit only the defined correction/fallback. ParadeDB outage/version mismatch/timeout records `bm25_unavailable` and visibly degrades to dense plus exact/trigram term search. Also record `dense_unavailable`, `term_unavailable`, `auth_context_invalid`, `retrieval_empty`, and `retrieval_timeout` when those paths fire. Return at most 12 evidence units.
13. Dispatch typed CSV/XLSX aggregation to the deterministic StructuredTable executor; never calculate totals from retrieved prose.

## Accuracy discipline

- Never tune on the final holdout.
- Persist profile fields/confidence/provenance, channel/candidate ranks, BM25 index/normalization version/projection lag/scanned/rechecked/degradation, fused rank, factors, rerank decision/result/counterfactual, selected parent, coverage/refusal, latency, and filters.
- Add fixtures for raw/normalized Arabic BM25 forms, bilingual/mixed language, identifiers, seeded aliases, selective BM25/HNSW filters, stale ACL/current-version projection rows, conflicting dates, negation, exact quotes, query-syntax injection, duplicate clusters, BM25 outage/version mismatch, and low/contradictory/insufficient evidence.
- Before bulk embedding, compare small-1536 with large-1536 and reduced-large dimensions on a disjoint Arabic/mixed qualification slice; pin from per-language retrieval quality plus memory/cost/latency.
- Seed the term channel from an SME-approved private glossary/code/acronym import before evaluation; monthly curation is not its first population.
- Score every query-profile field independently and attribute the first failing stage.
- Test OpenAI reranker schema enforcement, unknown/duplicate IDs, timeout/budget fallback, call accounting, and proof that no local model dependency/runtime exists.
- Compare always-rerank top 20 against the conditional policy and run skipped-case counterfactuals before tightening triggers. Compare semantic-only, BM25-only, exact-term-only, dense+term BM25-outage degradation, naive union, RRF, reranked RRF, and final context selection.
- Tune `rrf_k`, per-profile weights/depths, rerank pool/triggers, MMR, context, and coverage/refusal thresholds on development data; freeze before one final holdout run.
- Do not add HyDE, RAPTOR, SPLADE, ColBERT, or learned-to-rank in v1; preserve extension points and require held-out evidence before promotion. Do not install `pg_search` in managed Supabase or substitute `ts_rank_cd` while claiming BM25.
- Do not claim improvement without recall/precision/nDCG/MRR, citation, latency, and cost evidence on the labeled dataset.
