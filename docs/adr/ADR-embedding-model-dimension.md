---
title: ADR — Embedding model and dimension experiment plan
adr_id: ADR-embedding-model-dimension
status: proposed
owner: engineering-lead
last-reviewed: 2026-08-12
---

# ADR: Embedding model/dimension (experiment plan only)

## Status

Experiment plan for Phase 2 — **no winner selected**.

## Required bake-off

Compare `text-embedding-3-small` @1536 vs `text-embedding-3-large` @1536 and ≥1 lower dimension via OpenAI `dimensions`, on a frozen Arabic/mixed + English slice disjoint from launch holdout. Pin winner model/snapshot or alias, dimension, `vector` vs `halfvec`, distance op, index version from Recall@10/MRR/nDCG, cost, latency, storage. Combined vector working set ≤60% DB RAM at envelope.

## Non-goals for this document

No fabricated measurements. No bulk embedding until Phase 2 gate passes.
