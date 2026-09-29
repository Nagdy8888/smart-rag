"""Unit tests for BM25 conjunction-first ranking and flat-score discard."""

from __future__ import annotations

from smart_rag_core.retrieval.bm25 import (
    bm25_query_token_count,
    bm25_scores_discriminate,
    prefer_bm25_conjunction,
    resolve_bm25_operators,
)
from smart_rag_core.retrieval.profiles import Bm25Operator


def test_multi_token_prefers_conjunction_before_disjunction() -> None:
    """Long English asks try ``&&&`` before ``|||`` so scores can separate."""

    query = (
        "In the company document Building Applications with AI Agents, "
        "what Redis port and stream name does the supervisor publish tasks to?"
    )
    assert bm25_query_token_count(query) >= 2
    assert prefer_bm25_conjunction(query) is True
    assert resolve_bm25_operators(
        query, requested=Bm25Operator.MATCH_DISJUNCTION
    ) == (
        Bm25Operator.MATCH_CONJUNCTION,
        Bm25Operator.MATCH_DISJUNCTION,
    )


def test_single_token_stays_disjunction_only() -> None:
    """One-token asks keep the requested disjunction without a conjunction probe."""

    assert prefer_bm25_conjunction("Redis") is False
    assert resolve_bm25_operators(
        "Redis", requested=Bm25Operator.MATCH_DISJUNCTION
    ) == (Bm25Operator.MATCH_DISJUNCTION,)


def test_requested_conjunction_is_not_expanded() -> None:
    """An explicit conjunction request is returned alone."""

    assert resolve_bm25_operators(
        "port stream", requested=Bm25Operator.MATCH_CONJUNCTION
    ) == (Bm25Operator.MATCH_CONJUNCTION,)


def test_flat_equal_scores_do_not_discriminate() -> None:
    """Identical rounded scores must not enter Hybrid fusion."""

    assert bm25_scores_discriminate(()) is True
    assert bm25_scores_discriminate((1.5,)) is True
    assert bm25_scores_discriminate((2.0, 2.0, 2.0)) is False
    assert bm25_scores_discriminate((2.0, 2.0000001, 2.0)) is False
    assert bm25_scores_discriminate((3.1, 2.0, 3.1)) is True


def test_distinct_queries_must_not_share_flat_score_heads() -> None:
    """Regression contract: flat BM25 heads are discarded, not fused.

    Two unrelated multi-token asks previously shared the same UUID-ordered
    BM25 head when every survivor scored equally. Discarding flat scores
    leaves dense-only fusion instead of query-independent BM25 pollution.
    """

    left = "How many tokens do Gemini 2.5 and GPT-4.1 support?"
    right = "What Redis port and stream name does the supervisor publish?"
    assert prefer_bm25_conjunction(left) is True
    assert prefer_bm25_conjunction(right) is True
    flat = (1.0,) * 12
    assert bm25_scores_discriminate(flat) is False
    ranked = (4.2, 3.1, 2.0, 1.5)
    assert bm25_scores_discriminate(ranked) is True
