---
title: ADR — Long-document rerank pool of 60
adr_id: ADR-hybrid-long-document-v5-pool
status: rejected
owner: engineering-lead
last-reviewed: 2026-10-13
approver: pending
approval_date: pending
audience: engineering, reviewers
---

# ADR: Long-document rerank pool of 60

## Status

`rejected` on 2026-10-13. The file stays pinned and loadable. The selector
stays on `hybrid_long_document_v4`.

## Context

`hybrid_long_document_v4` sends 20 passages to the reranker. The fused
list holds up to 100. On the three probe15 sets, six misses were in the
dense list and in that fused list, and absent from the rerank pool. The
default `RERANK_POOL_SIZE` of 20 and the v4 file stay unchanged.
`rerank_max_per_document` stays 20. Pins and exact-duplicate collapse stay
as in v4.

A pool of 60 is three times the v4 pool and still under the fused cap of
100. One rerank call would send up to 60 excerpts of 800 characters.
`RerankModelRequest` still rejects more than 20 candidate ids, so a larger
pool cannot complete a rerank call.

## Decision

1. Add immutable `hybrid_long_document_v5` with `rerank_pool_size` 60 and
   rollback `hybrid_long_document_v4`. Do not route to it.
2. Keep the exact-one and small-corpus long-document rules on v4.

## Measurement

Compared with `probe15-*-final` (`3_fusion_pool` 2, 3, 2 and strict 4/15,
5/15, 8/15), the routed trial `probe15-*-v5` was strict 0/15 on every set.
Every question stopped in `company_scope` with insufficient evidence. The
checkpoint detail was a rerank request validation error: the candidate
list had 29 ids and the request allows 20. That fails the keep bar (strict
drop of more than three on every set).

## Consequences

- Long-document asks stay on the pool of 20.
- Routing v5 again requires a rerank request that accepts the larger pool,
  then a new probe15 measurement.

## Links

- [HYBRID_TUNING.md](../retrieval/HYBRID_TUNING.md)
- [HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md)
- [GENERAL_ANSWER_QUALITY_2026-10.md](../evaluation/GENERAL_ANSWER_QUALITY_2026-10.md)
