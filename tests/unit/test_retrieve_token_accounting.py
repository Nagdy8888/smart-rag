"""Provider tokens from retrieve sends accumulate on the run ledger."""

from __future__ import annotations

from decimal import Decimal

from smart_rag_core.gateways.embedding import EmbeddingResponse
from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.retrieval.hybrid_run.budget import counted_retrieve_send
from smart_rag_core.retrieval.rerank import RerankFallbackReason, RerankUsage


def test_counted_retrieve_send_accumulates_embedding_tokens() -> None:
    """Ask Run Details must include provider embedding prompt tokens."""

    budget = QueryRetrieveBudget(
        remaining_model_calls=3,
        remaining_usd=Decimal("1.00"),
    )
    response = EmbeddingResponse(
        mode="openai",
        vectors=((0.0, 1.0),),
        provider_request_id="req-1",
        fixture_provenance="openai://embeddings/test",
        estimated_cost_usd=Decimal("0.001"),
        prompt_tokens=17,
    )
    result = counted_retrieve_send(
        budget,
        usage_kind="embedding",
        model_id="text-embedding-3-large",
        send=lambda: response,
    )
    assert result is response
    assert budget.prompt_tokens == 17
    assert budget.completion_tokens == 0
    assert budget.usage_kinds == ["embedding"]


def test_counted_retrieve_send_accumulates_rerank_usage() -> None:
    """Rerank provider usage is added to the retrieve ledger."""

    budget = QueryRetrieveBudget(
        remaining_model_calls=3,
        remaining_usd=Decimal("1.00"),
    )
    usage = RerankUsage(
        request_id="r1",
        model="gpt-4o-mini",
        input_tokens=50,
        output_tokens=3,
        model_calls=1,
    )
    triple = ((), usage, RerankFallbackReason.NONE)
    counted_retrieve_send(
        budget,
        usage_kind="rerank",
        model_id="gpt-4o-mini",
        send=lambda: triple,
    )
    assert budget.prompt_tokens == 50
    assert budget.completion_tokens == 3
    assert budget.usage_kinds == ["rerank"]


def test_counted_retrieve_send_skips_tokens_when_rerank_usage_missing() -> None:
    """Identity or fallback rerank without usage must not invent tokens."""

    budget = QueryRetrieveBudget(
        remaining_model_calls=3,
        remaining_usd=Decimal("1.00"),
    )
    counted_retrieve_send(
        budget,
        usage_kind="rerank",
        model_id="gpt-4o-mini",
        send=lambda: ((), None, RerankFallbackReason.NONE),
    )
    assert budget.prompt_tokens == 0
    assert budget.completion_tokens == 0
    assert budget.usage_kinds == ["rerank"]
