"""Unit tests for company-Ask diagnosis buckets and page signals."""

from __future__ import annotations

from decimal import Decimal

import pytest
from smart_rag_core.evaluation.company_ask_diagnosis import (
    aggregate_usage_rows,
    bool_feedback_score,
    build_diagnosis_signals,
    classify_ask_drop,
    failure_bucket_score,
    page_in_pages,
)


def test_page_in_pages_requires_measured_sides() -> None:
    """Missing gold page or page list stays unknown."""

    assert page_in_pages(None, (1, 2)) is None
    assert page_in_pages(3, None) is None
    assert page_in_pages(3, (1, 2, 3)) is True
    assert page_in_pages(3, (1, 2)) is False


def test_build_diagnosis_signals_names_retrieval_miss() -> None:
    """A gold page absent from fused ids becomes retrieval_miss."""

    signal = build_diagnosis_signals(
        outcome="wrong_phrasing",
        grounded=False,
        gold_page=18,
        cited_pages=(17,),
        fused_pages=(17, 19),
        rerank_pool_pages=(17,),
        selected_pages=(17,),
        kind="text",
    )
    assert signal.gold_page_cited is False
    assert signal.gold_page_in_fused is False
    assert signal.failure_bucket == "retrieval_miss"


def test_build_diagnosis_signals_names_phrasing_when_gold_cited() -> None:
    """Gold cited and fused with a wrong answer is a phrasing miss."""

    signal = build_diagnosis_signals(
        outcome="wrong_phrasing",
        grounded=False,
        gold_page=18,
        cited_pages=(18,),
        fused_pages=(18, 19),
        rerank_pool_pages=(18,),
        selected_pages=(18,),
    )
    assert signal.gold_page_cited is True
    assert signal.gold_page_in_fused is True
    assert signal.failure_bucket == "phrasing"


def test_feedback_score_helpers() -> None:
    """Boolean and bucket helpers map to LangSmith-friendly floats."""

    assert bool_feedback_score(True) == 1.0
    assert bool_feedback_score(False) == 0.0
    assert bool_feedback_score(None) is None
    assert failure_bucket_score("pass") == 1.0
    assert failure_bucket_score("phrasing") == 0.0
    assert (
        classify_ask_drop(
            outcome="wrong_phrasing",
            grounded=False,
            gold_page_in_fusion=False,
            citation_failures=(),
            gold_page_in_fused=True,
            gold_page_in_rerank_pool=False,
        )
        == "rerank_pool_drop"
    )


def test_aggregate_usage_rows_sums_cost_and_prefers_answer_model() -> None:
    """Usage aggregation sums tokens/cost and prefers the answer model id."""

    totals = aggregate_usage_rows(
        (
            {
                "usage_kind": "embedding",
                "model_id": "text-embedding-3-large",
                "prompt_tokens": 40,
                "completion_tokens": 0,
                "total_tokens": 40,
                "cost_usd": "0.000005",
            },
            {
                "usage_kind": "answer",
                "model_id": "gpt-4o-mini",
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "cost_usd": "0.001235",
            },
        )
    )
    assert totals.input_tokens == 140
    assert totals.output_tokens == 20
    assert totals.total_tokens == 160
    assert totals.total_cost_usd == Decimal("0.001240")
    assert totals.model_id == "gpt-4o-mini"
    metadata = totals.usage_metadata()
    assert metadata["input_tokens"] == 140
    assert metadata["output_tokens"] == 20
    assert metadata["total_cost"] == pytest.approx(0.00124)
