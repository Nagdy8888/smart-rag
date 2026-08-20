---
name: implement-lightrag-graph
description: Implements LightRAG indexing, PostgreSQL storage, entity rules, graph evidence mappings, workspace lifecycle, inspection, and Combined retrieval integration. Use for any LightRAG or graph evidence work.
---

# Implement LightRAG GraphRAG

Read the active Phase 5 wrapper and selected inline packet contract. Load Phase 3/4 handoff evidence only when that packet names it; do not load Phase 6 or release packets. Verify the pinned LightRAG source/docs before coding because storage and query contracts can change.

## Qualification gate

Before integrating:

1. Expose only project-owned `GraphRetriever`/`GraphIndexer` protocols to services and LangGraph nodes; LightRAG classes remain inside the adapter.
2. Prove the intended PostgreSQL storage classes work without Apache AGE against the local Supabase-compatible database.
3. Run `initialize_storages()` only as a reviewed bootstrap/migration step; prohibit runtime schema drift.
4. Prove namespace/workspace isolation and required schema/grants.
5. Pass precomputed high/low keywords and assert no hidden query keyword-model call occurs.
6. Prove insertion/deletion/rebuild behavior, source identifiers, and deterministic query limits.
7. Route every LightRAG LLM/embedding callback through the shared budgeted/traced gateway.

If any contract fails, stop at the adapter boundary. Do not guess private schemas or patch vendor tables directly.

## Evidence contract

- LightRAG is a lead generator, never the final answer generator.
- `global` mode yields steering topics only and may produce at most three bounded Hybrid expansions.
- Native entities, relations, descriptions, and summaries cannot become citations.
- Insert normalized text through the qualified async `ainsert` contract with `ids=[document_version_id]` and a unique non-secret opaque basename source token. Canonical identity comes from the explicit ID and application map; never require verbatim URI round-trip, pass signed URLs, or use deprecated custom-chunk insertion.
- `Graph Ready` requires:
  - LightRAG mutation complete;
  - `lightrag_chunk_map` built by exact hash/span, then bounded scoped matching;
  - `graph_evidence_map` built for application statement IDs;
  - mapping/support calibration and survival thresholds passed.
- Query-time resolution rechecks active workspace, graph eligibility, current version, deletion, ACL, and support threshold.
- Do not implement per-statement query-time Hybrid searches.
- If `graph_survival_ratio < 0.50`, relabel Combined to Hybrid with `graph_survival_below_threshold`; alert when its rolling value is below 0.80 across 20 Combined queries.
- When relevant company-visible Hybrid hits are not Graph Ready, increase Hybrid evidence weight and show “N relevant recent documents are not yet represented in the graph”; never disclose restricted/ineligible counts.

## Workspace lifecycle

Honor `updating`, `filtered_dirty`, and `quarantined` exactly as planned. Use one PostgreSQL advisory-lock single writer for mutations/rebuilds, health checks, and an atomic active-workspace switch.

Apply curated aliases, canonical labels, entity types, and do-not-merge rules during rebuild. Never silently merge ambiguous entities.

An embedding-model change builds and validates a parallel versioned workspace before an atomic switch; in-place mixed embeddings are forbidden.

## Tests

Cover entity collisions, aliases, no-merge rules, mapping thresholds, low survival, global steering, path bounds, insertion failure, old/new version switchover, deletion, ACL downgrade, rebuild, quarantine, and Hybrid fallback.
