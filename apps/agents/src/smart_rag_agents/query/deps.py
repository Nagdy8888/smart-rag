"""Optional runtime bindings for the query graph. Import constructs no clients."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import psycopg
from smart_rag_core.query_routing.branches import (
    GraphRetrieveLike,
    HybridRetrieveLike,
    TableExecuteLike,
)
from smart_rag_core.query_routing.preparation import PrepModelCaller


@dataclass(slots=True)
class QueryGraphDeps:
    """Injectable adapters for memory, prep, and retrieve nodes.

    All fields default to None so ``graph.py`` can compile without sockets or
    OpenAI clients. Tests and later packets bind real adapters.

    Attributes:
        connection: ``app_api`` connection for memory load and counted prep.
        hybrid_retriever: Direct Hybrid retrieve adapter.
        graph_retriever: Direct GraphRetriever adapter.
        table_executor: Direct structured-table adapter.
        model_caller: One structured rewrite-plus-profile adapter.
        force_model: Spend the one prep call even when deterministic.
        cancel_check: Cooperative cancellation probe.
        answer_prompt_text: Pinned ``answer_v1`` body when a live adapter runs.
        verifier_prompt_text: Pinned ``verifier_v1`` body when a live adapter runs.
        model_gateway: Optional ``ModelGateway``. Compile constructs none.
    """

    connection: psycopg.Connection | None = None
    hybrid_retriever: HybridRetrieveLike | None = None
    graph_retriever: GraphRetrieveLike | None = None
    table_executor: TableExecuteLike | None = None
    model_caller: PrepModelCaller | None = None
    force_model: bool = False
    cancel_check: Callable[[], bool] | None = None
    answer_prompt_text: str | None = None
    verifier_prompt_text: str | None = None
    model_gateway: object | None = None
