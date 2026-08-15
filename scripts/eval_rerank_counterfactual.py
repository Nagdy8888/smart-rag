"""Holdout-blind always-rerank versus conditional skip counterfactuals."""

from __future__ import annotations

import json
import math
from pathlib import Path
from uuid import UUID, uuid5

from smart_rag_core.evaluation.loader import load_open_splits
from smart_rag_core.evaluation.schema import EvaluationCase
from smart_rag_core.retrieval.rerank import (
    RerankPassage,
    apply_mmr,
    should_skip_trivial_exact,
)
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
)
from smart_rag_core.retrieval.types import RetrievalCandidate

_NS = UUID("12345678-1234-5678-1234-567812345678")
_ROOT = Path(__file__).resolve().parents[1]
_REPORT = _ROOT / "docs" / "evaluation" / "RERANK_COUNTERFACTUAL.md"


def _ndcg(ranked_ids: list[UUID], gold: set[UUID], *, k: int) -> float:
    """Compute nDCG@k with binary relevance.

    Args:
        ranked_ids: Ordered candidate IDs.
        gold: Relevant IDs.
        k: Cutoff.

    Returns:
        nDCG in ``[0, 1]``.
    """

    gains = [1.0 if item in gold else 0.0 for item in ranked_ids[:k]]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sorted(gains, reverse=True)
    idcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def _hit_at_k(ranked_ids: list[UUID], gold: set[UUID], *, k: int) -> float:
    """Return 1.0 when any gold ID appears in the top-k.

    Args:
        ranked_ids: Ordered candidate IDs.
        gold: Relevant IDs.
        k: Cutoff.

    Returns:
        1.0 or 0.0.
    """

    if not gold:
        return 0.0
    return 1.0 if gold.intersection(ranked_ids[:k]) else 0.0


def _coverage(ranked_ids: list[UUID], gold: set[UUID], *, k: int) -> float:
    """Fraction of gold IDs recovered in the top-k.

    Args:
        ranked_ids: Ordered candidate IDs.
        gold: Relevant IDs.
        k: Cutoff.

    Returns:
        Coverage in ``[0, 1]``.
    """

    if not gold:
        return 0.0
    return len(gold.intersection(ranked_ids[:k])) / len(gold)


def _synthetic_pool(case: EvaluationCase) -> tuple[list[RerankPassage], set[UUID]]:
    """Build a 10-passage pool from labeled evidence plus distractors.

    Args:
        case: Open-split evaluation case.

    Returns:
        Passages in a stable fused order and the gold ID set.
    """

    gold: list[UUID] = []
    for link in case.evidence_links:
        if link.chunk_id and link.visible_to_actor:
            gold.append(uuid5(_NS, link.chunk_id))
    gold_set = set(gold)
    passages: list[RerankPassage] = []
    for index in range(10):
        chunk_id = (
            gold[index] if index < len(gold) else uuid5(_NS, f"{case.case_id}-d{index}")
        )
        channels: frozenset[str]
        if index == 0 and gold:
            channels = frozenset({"bm25", "term"})
        elif index < len(gold):
            channels = frozenset({"dense"})
        else:
            channels = frozenset({"dense"})
        passages.append(
            RerankPassage(
                candidate=RetrievalCandidate(
                    chunk_id=chunk_id,
                    document_id=uuid5(_NS, f"{case.case_id}-doc-{index // 3}"),
                    version_id=uuid5(_NS, f"{case.case_id}-ver"),
                    channel_rank=index + 1,
                    channel_score=1.0,
                ),
                raw_text=case.query if index < len(gold) else f"distractor {index}",
                token_count=8,
                channels=channels,
                excerpt=case.query if index < len(gold) else f"distractor {index}",
            )
        )
    return passages, gold_set


def _mean(values: list[float]) -> float:
    """Average a list, or 0 when empty.

    Args:
        values: Samples.

    Returns:
        Arithmetic mean.
    """

    if not values:
        return 0.0
    return sum(values) / len(values)


def main() -> int:
    """Score development and qualification skip counterfactuals.

    Returns:
        Process exit code.

    Side Effects:
        Writes ``docs/evaluation/RERANK_COUNTERFACTUAL.md``. Never reads holdout.
    """

    cases = load_open_splits()
    skipped = 0
    reranked = 0
    top1_changed = 0
    ndcg_deltas: list[float] = []
    top1_always: list[float] = []
    top5_always: list[float] = []
    top1_skip: list[float] = []
    top5_skip: list[float] = []
    evidence_always: list[float] = []
    evidence_skip: list[float] = []
    citation_always: list[float] = []
    citation_skip: list[float] = []
    for case in cases:
        pool, gold = _synthetic_pool(case)
        skip = should_skip_trivial_exact(case.expected_profile, tuple(pool))
        always_ids = [item.candidate.chunk_id for item in pool]
        if skip:
            skipped += 1
            selected, _dropped = apply_mmr(tuple(pool), query=case.query)
            skip_ids = [item.candidate.chunk_id for item in selected]
            if always_ids[:1] != skip_ids[:1]:
                top1_changed += 1
            ndcg_deltas.append(
                _ndcg(always_ids, gold, k=5) - _ndcg(skip_ids, gold, k=5)
            )
            top1_always.append(_hit_at_k(always_ids, gold, k=1))
            top5_always.append(_hit_at_k(always_ids, gold, k=5))
            evidence_always.append(_coverage(always_ids, gold, k=5))
            citation_always.append(_coverage(always_ids, gold, k=12))
            top1_skip.append(_hit_at_k(skip_ids, gold, k=1))
            top5_skip.append(_hit_at_k(skip_ids, gold, k=5))
            evidence_skip.append(_coverage(skip_ids, gold, k=5))
            citation_skip.append(_coverage(skip_ids, gold, k=12))
        else:
            reranked += 1
    mean_delta = _mean(ndcg_deltas)
    report = f"""---
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
support. Packet 6 may retune skip triggers after a live always-rerank reference.

| Field | Value |
| --- | --- |
| Prompt | `{RERANK_PROMPT_VERSION}` SHA-256 `{RERANK_PROMPT_SHA256}` |
| Model | mock identity / pin `gpt-4o-mini` unused |
| Open-split cases | {len(cases)} |
| Conditionally skipped | {skipped} |
| Always reranked (non-trivial) | {reranked} |
| Skip cases with top-1 change vs always-RRF | {top1_changed} |
| Mean nDCG@5 (always - skip) on skip cases | {mean_delta:.4f} |
| Mean hit@1 always / skip (skip cases) | {_mean(top1_always):.4f} / {_mean(top1_skip):.4f} |
| Mean hit@5 always / skip (skip cases) | {_mean(top5_always):.4f} / {_mean(top5_skip):.4f} |
| Mean evidence coverage@5 always / skip (skip cases) | {_mean(evidence_always):.4f} / {_mean(evidence_skip):.4f} |
| Mean citation support@12 always / skip (skip cases) | {_mean(citation_always):.4f} / {_mean(citation_skip):.4f} |
| Mean latency delta (ms) | 0 (mock) |
| Mean cost delta (tokens) | 0 (mock; one call reserved only when reranked) |
| Live OpenAI contract | not configured (`MOCK_MODEL_MODE=true`) |

Identity mock implies skip-versus-always ranking deltas come only from MMR/quotas,
not from a provider permutation.

Related: [HYBRID_RETRIEVAL_CONTRACT.md](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md) ·
[phase-04-hybrid-rag-evidence.md](../development/phase-04-hybrid-rag-evidence.md) ·
[docs index](../README.md)
"""
    _REPORT.write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {
                "skipped": skipped,
                "reranked": reranked,
                "cases": len(cases),
                "mean_ndcg_delta": mean_delta,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
