---
title: ADR — Allow-listed long-document Hybrid profile
adr_id: ADR-hybrid-long-document-profile
status: proposed
owner: engineering-lead
last-reviewed: 2026-09-09
approver: pending
approval_date: pending
audience: engineering, reviewers, security
---

# ADR: Allow-listed long-document Hybrid profile

## Status

`proposed` — overlay Gate 0 records the decision for later Packet 14 freeze.
It is not a production v1 authorization and does not change
`hybrid_default_v1`.

## Context

Production Hybrid retrieve (`ProcessHybridRetriever`) does not inject the
qualified OpenAI reranker. Frozen `hybrid_default_v1` keeps a 20-candidate
pool, five passages per document in that pool, two-passage final document
quota, first-400-character excerpts, and lexical Jaccard MMR. Those values
were qualified on a compact synthetic corpus with identity rerank
([PHASE4_RANKED_IDS.md](../evaluation/PHASE4_RANKED_IDS.md)). One long
authorized PDF cannot fill useful final evidence under a two-passage
document quota, and a global quota change would retune every workspace.

## Decision

1. Keep `hybrid_default_v1` byte-for-byte until open-split regression
   evidence permits a change. Add a separate immutable candidate
   `hybrid_long_document_v1`.
2. Runtime `load_frozen_profile()` rejects the long-document id until Packet
   14 freezes its hash and selector. An unfrozen candidate fails closed to
   `hybrid_default_v1`.
3. Select the long profile only when the server resolves exactly one
   authorized current version, representative-passage count is greater
   than five, and the frozen selector allow-lists the query class. Trivial
   exact lookups stay on default unless measured evidence promotes them.
   Ambiguous or unauthorized source references never become hard SQL filters.
4. Long-document candidate derivation (not a global constant change):
   per-document rerank cap = 20 (the existing pool); final document quota =
   12 (the existing evidence cap); section quota starts at 2 and is
   evaluated; global 20/12/3500 ceilings stay unchanged.
5. Long-profile MMR uses validated rerank order (or RRF on fallback) as
   relevance; normalized Jaccard is a duplicate penalty only; UUID is a
   final exact-tie break.
6. Reject: enlarging default quotas for all documents; hardcoding this
   PDF's title or SHA-256 into retrieval; map-reduce, recursive, or RAPTOR
   summaries; local cross-encoders; treating unsealed model-draft labels as
   gold.

## Consequences

- Overlay Packets 9–12 may inject an evaluation candidate. Runtime allow-list
  change is Packet 14 only.
- Phase 6 Packet 10 binds the OpenAI reranker and source resolver. Until
  freeze, that binding is proven under `hybrid_default_v1`.
- Qualification of this PDF is not generalization to other documents.

## Links

- [hybrid-pdf-accuracy-remediation.md](../development/hybrid-pdf-accuracy-remediation.md)
- [ADR-phase4-engineering-close.md](./ADR-phase4-engineering-close.md)
- [HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md)
- [PROHIBITED_V1_METHODS.md](../retrieval/PROHIBITED_V1_METHODS.md)
- [docs index](../README.md)
