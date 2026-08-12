---
title: ADR — Embedding model and dimension
adr_id: ADR-embedding-model-dimension
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-12
---

# ADR: Embedding model and dimension

## Status

**Accepted** for Phase 2 Packet 1 after live bake-off on frozen slice `embedding-qual-v1`.

## Decision

| Field | Pin |
| --- | --- |
| Model | `text-embedding-3-large` (OpenAI API id; snapshot as returned by API) |
| Dimensions | `1024` via `dimensions` parameter |
| Storage type | `vector` (float32); `halfvec` reserved if DB RAM cannot meet 60% working-set gate |
| Distance | cosine (`vector_cosine_ops` / `<=>`) |
| Index | HNSW with pgvector ≥0.8 iterative scans (`hnsw.iterative_scan`) |
| Rollback | Re-embed with prior candidate only through a versioned embedding column + rebuild job |
| Rebuild trigger | Model/dimension/type change, or corruption/version mismatch |

## Context

Live comparison (see [EMBEDDING_QUALIFICATION_REPORT.md](../evaluation/EMBEDDING_QUALIFICATION_REPORT.md)):

- `text-embedding-3-small` @1536
- `text-embedding-3-large` @1536
- `text-embedding-3-large` @1024

All three reached Recall@10 = 1.0 on the frozen slice. Large@1536 and large@1024 matched or beat small on Arabic MRR/nDCG. Large@1024 preserves large-model quality with one-third fewer dimensions than 1536.

## Memory math (full Hybrid envelope)

Assumptions: 1,000,000 Hybrid chunks + 200,000 graph source chunks (LightRAG), float32, HNSW size ≈ 1.8× raw vectors.

| Component | Raw vectors | ×1.8 HNSW |
| --- | --- | --- |
| Hybrid @1024 | 4.10 GB | 7.37 GB |
| LightRAG @1024 | 0.82 GB | 1.47 GB |
| **Combined** | 4.92 GB | **8.84 GB** |

60% working-set gate ⇒ database RAM ≥ **14.7 GB** (plan for **≥16 GB** usable RAM) before bulk embed. If the selected managed tier is smaller, enable `halfvec` qualification or reduce envelope before ingestion—do not silently proceed.

## Alternatives considered

- **small@1536:** lower cost; weaker Arabic MRR on this slice (0.917 vs 1.000).
- **large@1536:** best metrics; ~50% more vector RAM than 1024 with no Recall@10 gain here.
- **halfvec now:** deferred pending tier RAM decision; same metrics protocol required.

## Consequences

Bulk embedding and HNSW build are blocked until the selected Supabase tier (or `halfvec`) satisfies the RAM gate. Schema Packet 2 must use dimension **1024** `vector` columns matching this ADR.
