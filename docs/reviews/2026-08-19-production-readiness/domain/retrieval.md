---
title: Domain review — retrieval, graph, citations
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, reviewers, client-approver
reviewed_commit: 09a102a
---

# Domain: retrieval and GraphRAG

Canonical findings: [critical](../01-critical.md) C-005 C-006 C-009 · [high](../02-high.md) H-010 H-012 H-024 H-029 · [medium](../03-medium.md) M-003 M-004 M-007 M-027 · [low](../04-low.md) L-013.

## Invariants vs code

| Invariant | Code | Proof |
| --- | --- | --- |
| BM25 snippets never evidence | Retriever returns IDs; recheck in Supabase | Contract tests **in the library** |
| Graph prose never evidence | Mapping resolver + fusion assemble | Fail-closed constants; empty locator text remains (H-024) |
| ACL recheck before use | `recheck_retrieval_candidates` | Tests; **not on live SSE** (C-009) |
| Live chat uses Hybrid | `QueryGraphDeps` in SSE | **Unbound** — `retrievers_unbound` |
| Arabic normalizer shared | `search.normalize_arabic_v1` + core | Hybrid parity tests; graph entity keys use a different normalizer |
| Citation IDs must be in evidence | `filter_invented_ids` + deterministic | Unit; empty span can pass; live faithfulness Not Run |
| Prohibited v1 methods | Docs + frozen profile | Do not add HyDE/SPLADE in a panic to fix H-010 |

## Quality verdict (harsh)

The retrieval **libraries** are production-shaped. The retrieval **runtime and scores** are not:

- Production SSE does not call Hybrid/Graph/table retrievers (C-009). Quality gates measured by `scripts/eval_phase4_ranked_ids.py` do not apply to chat.
- Packet 9 Recall@10 used identity rerank (`rerank_call_count=0`). Do not quote those percents as OpenAI-reranked Hybrid.
- Locator correctness 1.0 on n=7 is "we can point at a chunk" on a synthetic open split.
- Hybrid Recall@10 **0.25** is "we often cannot find the chunk."
- Alias Recall@10 **0.0** is a launch-killing miss for a glossary/alias product.
- Combined ≥10 pp multi-hop (QT-EVAL-009) is explicitly `unverified`. Keep Hybrid default.
- Holdout sealed means you cannot measure the number you would be judged on.

Fix ranking/normalization/glossary on the open split. Then cut a **new** holdout. Using the sealed file because "we need a number" would contaminate the only honest exam.

## Combined / Graph

Shared LightRAG workspace + company-visible-only graph eligibility is the right ACL story. It does not make Combined a default Auto route until survival, fusion ablation, and +10 pp are live. Keep Auto → Hybrid. Offer Combined in an advanced panel if you must demo.

## Tables

Deterministic structured table path exists (`packages/core/.../tables`). Numeric invention from prose is forbidden by plan. Prove QT-LAT-006 on real Parquet artifacts; Phase 9 noted table executed 0/1 when Parquet dir missing.
