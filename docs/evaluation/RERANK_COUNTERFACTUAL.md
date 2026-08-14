---
title: Phase 4 Packet 5 rerank counterfactuals
owner: engineering-lead
status: draft
last-reviewed: 2026-08-14
audience: engineering, reviewers
---

# Rerank always-versus-conditional counterfactuals

Holdout was not read. The reranker is the mock identity adapter
(`MOCK_MODEL_MODE=true`), so always-rerank order equals fused RRF order.
Conditional skips apply MMR/quotas only. Live OpenAI deltas are **unverified**.
Latency and token cost are 0 under the mock identity adapter.

Term/subquestion coverage uses labeled gold chunk IDs as a proxy for citation
support. Packet 6 did **not** retune skip triggers, channel depths, or RRF
weights; those still need live ranked-ID evidence.

| Field | Value |
| --- | --- |
| Prompt | `rerank_v1` SHA-256 `4767049107cfe6e8591c84d3b1d202393dfd2564383e6c5bfa0bd5fece8f1925` |
| Model | mock identity / pin `gpt-4o-mini` unused |
| Open-split cases | 293 |
| Conditionally skipped | 43 |
| Always reranked (non-trivial) | 250 |
| Skip cases with top-1 change vs always-RRF | 0 |
| Mean nDCG@5 (always - skip) on skip cases | 0.0000 |
| Mean hit@1 always / skip (skip cases) | 1.0000 / 1.0000 |
| Mean hit@5 always / skip (skip cases) | 1.0000 / 1.0000 |
| Mean evidence coverage@5 always / skip (skip cases) | 1.0000 / 1.0000 |
| Mean citation support@12 always / skip (skip cases) | 1.0000 / 1.0000 |
| Mean latency delta (ms) | 0 (mock) |
| Mean cost delta (tokens) | 0 (mock; one call reserved only when reranked) |
| Live OpenAI contract | not configured (`MOCK_MODEL_MODE=true`) |

Identity mock implies skip-versus-always ranking deltas come only from MMR/quotas,
not from a provider permutation.

Related: [HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md) ·
[phase-04-hybrid-rag-evidence.md](../development/phase-04-hybrid-rag-evidence.md) ·
[docs index](../README.md)
