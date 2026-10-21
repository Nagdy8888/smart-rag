# Ingestion, retrieval, graph, and structured-data review

See [scope and evidence conventions](README.md). Verdict: **strong canonical-data design, with newer native-PDF processing bypassing some controls**.

## Pipeline and useful boundaries

The intended path is upload reservation/finalization or approved crawl, durable job claim, current scan evidence, constrained parse, extraction governance, canonical chunk/table/figure materialization, budgeted external processing, and derived-index publication. Worker leases, operation keys, and canonical visibility determine which versions can be used.

`apps/worker/src/smart_rag_worker/lifecycle.py` handles durable graph execution and patches a resumed checkpoint with the current lease token. That is a valuable protection against replaying writes with an expired token. The main index graph checks current scan evidence before processing. Ingestion is not just an upload handler launching an untracked background task.

## Canonical retrieval

Dense, BM25, and exact/term channels are fused, with reranking and context fitting. `retrieval/recheck.py` reauthorizes derived IDs through Supabase and bounds the batch. `retrieval/cache_key.py` includes principal scope, visibility generation, index/profile, and normalizer/prompt versions; cache payloads store IDs/ranks rather than raw snippets.

These controls are appropriate because ACL/version state can change independently of a search index. A stale BM25 hit or cached ID must never become evidence merely because it had a good score. Keep the primary authorization check after derived retrieval even when optimizing latency.

The retrieval codebase is complex: long-document profiles, page scoping, native content, reranking, parent expansion, and salvage all interact. Large `retrieval/rerank.py` and graph adapters increase the cost of reasoning about changes. Prefer stage-based evaluation and fixed regression sets over adding one heuristic per miss.

## Graph evidence

The design treats LightRAG relationships as candidate/steering information and resolves answer evidence back to canonical chunks. This is a sound trust boundary. Runtime adapter binding is separate from schema initialization, and graph readiness can degrade independently of Hybrid.

**Verification gap:** no live graph ACL downgrade, deleted/current-version transition, entity leakage, provider failure, or mapping-survival integration test was performed in this review. The presence of mapping/recheck code is not proof of the deployed graph projection's correctness.

Recommended graph acceptance scenario: index a company-visible document, ask a relationship question, downgrade/delete it, then prove entity inspection, relationship traversal, cached candidates, and historical citation access behave according to the contract. Use a second user who never had access as a negative control.

## Structured tables

The actual query executor is under `smart_rag_core/tables`, not the older ingestion fixture sandbox. `tables/plan.py` and `builder.py` use typed operations, allow-listed identifiers, and positional values. `tables/executor.py` starts a separate child process with a stripped environment and timeout/kill behavior. `tables/sandbox_worker.py` verifies the exact artifact path/hash, loads it, disables external access, locks configuration, bounds rows/output bytes, and returns provenance.

This is materially stronger than executing model-generated SQL or asking a model to infer a sum from a large pasted table. Preserve deterministic computation and source ranges.

**Verification gaps:** current hosted manifest authorization, row-level provenance correctness after aggregations, malformed artifact handling, and deployed OS limits were not exercised end to end. A process sandbox also needs correct filesystem/network/resource isolation in its actual runtime; the Python API alone cannot prove that.

## Native PDFs: the highest-risk extension

**SEC-01:** figure descriptions bypass the complete external-provider governance and accounting boundary. Figure materialization occurs before canonical-operation replay checks, so a retry may repeat provider work despite an existing canonical result. Move replay checks and authorized/countable provider admission ahead of all outbound work.

**SEC-02:** figures reopen/crop the original PDF outside the parser sandbox. Citation page previews also reopen originals in the API. One intended isolation boundary now has multiple exceptions. Treat render/crop as untrusted document processing even after ClamAV passes.

**AG-05:** verified native code/table blocks can be truncated by the later organizer. A perfect parser cannot prevent content loss after generation if the release layer slices away exact blocks.

**Additional correctness risk to investigate:** materialized figure text joins a nearby caption with a vision-generated description and becomes indexable text. Preserve separate provenance for original source text and model description so downstream verification does not mistake a generated interpretation for a literal PDF statement. The artifact model retains caption/description fields, which is a useful foundation; a full downstream provenance audit was not completed here.

## Re-ingestion and migrations

Parser/version changes cannot repair already stored passages through a frontend change. Keep parser version, chunking configuration, normalization, embedding model, and derived-index versions attached to artifacts. After native parsing or table changes, select a representative corpus for re-ingestion and compare canonical output before flipping visibility.

Do not edit applied migrations to fix metadata or ACL behavior. Use additive migrations and prove both upgrade behavior and least-privilege grants on an isolated hosted test target. No migrations were applied during this review.

## Recommended data-quality gates

1. A mixed PDF corpus with ordinary text, page labels, multi-column text, code, dense tables, figures, rotated/oversize pages, and Arabic.
2. Parse-output checks before retrieval scoring: source text, locators, labels, figure artifacts, and table schema/provenance.
3. A canonical visibility/ACL transition test across all derived projections and caches.
4. An ingestion crash/retry test proving no duplicate provider spend or mismatched lease writes.
5. Retrieval recall at candidate and fused-context stages, followed by final answer and citation-page metrics.
6. Structured-table negative tests for foreign manifests, traversal, network/extension attempts, oversized output, and aggregate provenance.

Keep these stages separate: missing parsed text, missed retrieval, context eviction, omitted draft claims, rejected verification, and unresolved citation leaves require different fixes.
