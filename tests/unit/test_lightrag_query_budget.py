"""LightRAG query callbacks consume the run-local retrieve budget."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import numpy as np
import pytest
from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.gateways.model import create_model_gateway
from smart_rag_core.query_admission.ceilings import QueryRetrieveBudget
from smart_rag_core.query_admission.exceptions import QueryBudgetError
from smart_rag_core.retrieval.lightrag_adapter import (
    _QUERY_RETRIEVE_BUDGET,
    install_query_budget_consume,
)
from smart_rag_core.retrieval.lightrag_callbacks import CountedLightRagCallbacks
from smart_rag_core.settings import AgentSettings


def _callbacks() -> CountedLightRagCallbacks:
    """Build counted callbacks with mock gateways.

    Returns:
        Callbacks with query-budget consume wrappers installed.
    """

    settings = AgentSettings()
    callbacks = CountedLightRagCallbacks(
        embedding_gateway=create_embedding_gateway(settings),
        model_gateway=create_model_gateway(settings),
    )
    install_query_budget_consume(callbacks)
    return callbacks


def test_lightrag_embedding_callback_debits_retrieve_budget() -> None:
    """Query-time LightRAG embed consumes remaining model calls and USD."""

    callbacks = _callbacks()
    budget = QueryRetrieveBudget(
        remaining_model_calls=8,
        remaining_usd=Decimal("3.20"),
    )

    async def _run() -> object:
        """Invoke one embedding callback under the retrieve budget.

        Returns:
            Embedding matrix.
        """

        token = _QUERY_RETRIEVE_BUDGET.set(budget)
        try:
            return await callbacks.embedding_texts(["atlas controller"])
        finally:
            _QUERY_RETRIEVE_BUDGET.reset(token)

    vectors = asyncio.run(_run())
    assert isinstance(vectors, np.ndarray)
    assert budget.usage_kinds == ["embedding"]
    assert budget.remaining_model_calls == 7
    assert budget.remaining_usd == Decimal("3.18")


def test_lightrag_callback_fails_closed_when_reservation_short() -> None:
    """LightRAG consume does not debit or succeed when remaining cannot cover."""

    callbacks = _callbacks()
    budget = QueryRetrieveBudget(
        remaining_model_calls=8,
        remaining_usd=Decimal("0.01"),
    )

    async def _run() -> None:
        """Attempt one embedding callback that must fail closed."""

        token = _QUERY_RETRIEVE_BUDGET.set(budget)
        try:
            await callbacks.embedding_texts(["atlas controller"])
        finally:
            _QUERY_RETRIEVE_BUDGET.reset(token)

    with pytest.raises(QueryBudgetError, match="reservation_exhausted"):
        asyncio.run(_run())
    assert budget.usage_kinds == []
    assert budget.remaining_model_calls == 8
    assert budget.remaining_usd == Decimal("0.01")
