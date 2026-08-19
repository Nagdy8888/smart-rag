"""Optional runtime bindings for the query graph. Import constructs no clients."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import psycopg

# isort: off
# hybrid_run must finish before query_admission package init (ceilings cycle).
import smart_rag_core.retrieval.hybrid_run as _hybrid_run_cycle_guard  # noqa: F401
from smart_rag_core.query_routing.branches import (
    GraphRetrieveLike,
    HybridRetrieveLike,
    TableExecuteLike,
)

# isort: on
from smart_rag_core.query_routing.preparation import PrepModelCaller
from smart_rag_core.security.identity import UserRole
from smart_rag_core.tools.compare import RUNTIME_SELECTION_POLICY
from smart_rag_core.tools.models import SelectionPolicy


@dataclass(slots=True)
class QueryGraphDeps:
    """Injectable adapters for memory, prep, retrieve, and optional tools.

    All fields default so Studio ``graph.py`` can compile without sockets
    or OpenAI clients. Live FastAPI SSE binds Hybrid, gateway, prompts,
    and a per-run ``app_api`` connection via
    ``smart_rag_api.services.query_graph_runtime``. Do not share
    ``cancel_check`` or ``connection`` across concurrent compiled graphs.

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
        optional_policy: Frozen mapping-versus-discovery policy.
        force_discovery: Test hook for the one catalog round.
        chat_model: Optional langchain-core chat model for next-call bind.
        live_role_override: Test hook for role-change-after-plan.
        last_bound_runnable: Last next-call bind, for contract tests.
        unbound_model: Original model after bind, for unbind proofs.
        store_get: Optional LangGraph store reader for compact summaries.
        store_put: Optional LangGraph store writer for compact summaries.
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
    optional_policy: SelectionPolicy = RUNTIME_SELECTION_POLICY
    force_discovery: bool = False
    chat_model: object | None = None
    live_role_override: UserRole | None = None
    last_bound_runnable: object | None = field(default=None)
    unbound_model: object | None = field(default=None)
    store_get: (
        Callable[[tuple[str, str, str], str], dict[str, object] | None] | None
    ) = None
    store_put: Callable[[tuple[str, str, str], str, dict[str, object]], None] | None = (
        None
    )
