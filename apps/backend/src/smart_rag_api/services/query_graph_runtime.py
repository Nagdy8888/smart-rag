"""FastAPI-owned wiring for live SSE query-graph adapters.

Studio's module-level ``graph`` stays checkpointer-free and unbound. This
module constructs Hybrid, optional LightRAG, structured-table, prompts, and
the counted model gateway for the FastAPI executor only. It imports no
FastAPI routers; adapters come from settings and optional ``app.state``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg

# isort: off
# hybrid_run must finish before query_admission package init (ceilings cycle).
from smart_rag_core.retrieval.hybrid_run import HybridRetriever
from smart_rag_agents.prompts import answer_prompt_text, verifier_prompt_text
from smart_rag_agents.query.deps import QueryGraphDeps

# isort: on
from smart_rag_core.evaluation.schema import ExpectedProfile
from smart_rag_core.gateways.embedding import EmbeddingGateway, create_embedding_gateway
from smart_rag_core.gateways.model import (
    ModelGatewayUnavailableError,
    create_model_gateway,
)
from smart_rag_core.query_routing.branches import (
    GraphRetrieveLike,
    HybridRetrieveLike,
    TableExecuteLike,
)
from smart_rag_core.query_routing.models import BranchSpec
from smart_rag_core.retrieval.bm25 import Bm25Retriever
from smart_rag_core.retrieval.context_loader import (
    ChunkContext,
    fetch_authorized_chunk_context,
)
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.settings import SharedSettings, load_backend_settings
from smart_rag_core.tables.executor import TableSandboxError
from smart_rag_core.tables.refusals import TableQueryRefusal
from smart_rag_core.tables.resolver import PostgresTableResolver, TableResolveError
from smart_rag_core.tables.service import StructuredTableError, structured_table_query


class QueryGraphRuntimeError(RuntimeError):
    """Live SSE cannot compile an unbound query graph.

    Attributes:
        reason: Stable machine-readable code. Never a secret or DSN.
    """

    def __init__(self, reason: str) -> None:
        """Store one fail-closed runtime reason.

        Args:
            reason: Short identifier for logs and SSE ``error.code``.
        """

        super().__init__(reason)
        self.reason = reason


_LIGHTRAG_BUDGET_LOCK: asyncio.Lock | None = None


def _lightrag_budget_lock() -> asyncio.Lock:
    """Return the process lock that serializes Combined ``query_budget`` bind.

    Returns:
        Loop-safe lock created on first Combined retrieve.
    """

    global _LIGHTRAG_BUDGET_LOCK
    if _LIGHTRAG_BUDGET_LOCK is None:
        _LIGHTRAG_BUDGET_LOCK = asyncio.Lock()
    return _LIGHTRAG_BUDGET_LOCK


@dataclass(slots=True)
class QueryGraphProcessBindings:
    """Process-reusable adapters. Per-run cancel and ``app_api`` connections stay off this object.

    Attributes:
        hybrid_retriever: DSN-based Hybrid retrieve. Channel threads open
            their own Postgres connections.
        model_gateway: Counted gateway. Mock mode is still a gateway.
        graph_retriever: Process LightRAG adapter, or None when unbound.
        table_executor: Structured-table path using ``app_api`` ACL.
        answer_prompt_text: Pinned ``answer_v1`` body.
        verifier_prompt_text: Pinned ``verifier_v1`` body.
        supabase_dsn: Canonical Postgres URL for per-run ``app_api`` connections.
    """

    hybrid_retriever: HybridRetrieveLike
    model_gateway: object
    graph_retriever: GraphRetrieveLike | None
    table_executor: TableExecuteLike | None
    answer_prompt_text: str
    verifier_prompt_text: str
    supabase_dsn: str


class _DsnChannelMarker:
    """Truthy Hybrid channel flag. Per-channel jobs open their own DSN connections.

    Attributes:
        retrieve: Unused placeholder. ``HybridRetriever`` reconstructs dense
            and term adapters when ``supabase_dsn`` is set.
    """

    retrieve = None


class DsnBm25Retriever:
    """ParadeDB BM25 adapter that opens one connection per retrieve.

    Concurrent Hybrid channel threads must not share a ``psycopg`` connection.
    """

    def __init__(self, parade_dsn: str) -> None:
        """Store the unpublished ParadeDB URL.

        Args:
            parade_dsn: ``PARADEDB_URL`` secret value.
        """

        self._parade_dsn = parade_dsn

    def retrieve(
        self,
        *,
        supabase: psycopg.Connection,
        caller: CallerContext,
        query_text: str,
    ) -> object:
        """Scan BM25 IDs on a fresh ParadeDB connection.

        Args:
            supabase: Canonical connection used only for ACL recheck.
            caller: Server-derived caller.
            query_text: Raw query.

        Returns:
            ``Bm25RetrievalResult``. Hybrid catches connection failures and
            degrades to dense plus term.

        Side Effects:
            Opens and closes one ParadeDB connection.
        """

        with psycopg.connect(self._parade_dsn, connect_timeout=8) as parade:
            return Bm25Retriever(parade).retrieve(
                supabase=supabase,
                caller=caller,
                query_text=query_text,
            )


class ProcessHybridRetriever:
    """Hybrid retrieve that reuses the embedding gateway and opens per-call DB connections.

    ``HybridRetriever`` context loading captures the retrieve caller, so each
    ``retrieve`` builds an inner retriever. Dense/term/BM25-recheck threads
    still use ``supabase_dsn``.
    """

    def __init__(
        self,
        *,
        embedding_gateway: EmbeddingGateway,
        supabase_dsn: str,
        bm25: DsnBm25Retriever | None,
    ) -> None:
        """Bind the process embedding gateway and DSNs.

        Args:
            embedding_gateway: Shared ``EmbeddingGateway``.
            supabase_dsn: Full canonical Postgres URL including password.
            bm25: Optional per-retrieve ParadeDB adapter. ``None`` degrades
                BM25 (approved dense+term Hybrid).
        """

        self._embedding_gateway = embedding_gateway
        self._supabase_dsn = supabase_dsn
        self._bm25 = bm25
        self.query_budget: object | None = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
        query_budget: object | None = None,
    ) -> object:
        """Run one Hybrid retrieve with per-channel connections.

        Args:
            query: Branch query text.
            caller: Server-derived caller.
            profile: Typed query profile when present.
            deadline_seconds: Remaining retrieval slice.
            query_budget: Optional per-run retrieve ledger. Copied onto the
                inner retriever so concurrent SSE runs do not share it.

        Returns:
            ``HybridRunResult`` with ranked IDs. BM25 snippets are never evidence.

        Side Effects:
            Embedding gateway call plus per-channel Postgres (and optional
            ParadeDB) connections.
        """

        typed_profile = profile if isinstance(profile, ExpectedProfile) else None
        inner = HybridRetriever(
            embedding_gateway=self._embedding_gateway,
            supabase=None,
            paradedb=None,
            supabase_dsn=self._supabase_dsn,
            dense=_DsnChannelMarker(),
            bm25=self._bm25,
            term=_DsnChannelMarker(),
            load_context=_context_loader(self._supabase_dsn, caller),
        )
        budget = query_budget if query_budget is not None else self.query_budget
        inner.query_budget = budget  # type: ignore[assignment]
        return inner.retrieve(
            query=query,
            caller=caller,
            profile=typed_profile,
            deadline_seconds=deadline_seconds,
        )


@dataclass(slots=True)
class _RunScopedHybrid:
    """Per-run Hybrid facade. ``query_budget`` must not live on the process adapter.

    Attributes:
        inner: Process DSN-based Hybrid.
        query_budget: Set by ``execute_branches`` for this compiled run only.
    """

    inner: ProcessHybridRetriever
    query_budget: object | None = None

    def retrieve(
        self,
        *,
        query: str,
        caller: CallerContext,
        profile: object | None = None,
        deadline_seconds: float | None = None,
    ) -> object:
        """Forward retrieve with this run's budget.

        Args:
            query: Branch query text.
            caller: Server-derived caller.
            profile: Typed query profile when present.
            deadline_seconds: Remaining retrieval slice.

        Returns:
            ``HybridRunResult``.
        """

        return self.inner.retrieve(
            query=query,
            caller=caller,
            profile=profile,
            deadline_seconds=deadline_seconds,
            query_budget=self.query_budget,
        )


class _RunScopedGraph:
    """Per-run LightRAG facade so ``query_budget`` is not shared across SSE runs."""

    def __init__(self, adapter: GraphRetrieveLike) -> None:
        """Wrap one process graph adapter.

        Args:
            adapter: Lifespan LightRAG adapter.
        """

        self._adapter = adapter
        self.query_budget: object | None = None

    async def _forward(
        self,
        method_name: str,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Bind this run's ledger, then invoke one adapter retrieve.

        Args:
            method_name: ``retrieve_local``, ``retrieve_hybrid``, or
                ``retrieve_global_steering``.
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads. Never evidence.
        """

        method = getattr(self._adapter, method_name)
        async with _lightrag_budget_lock():
            self._adapter.query_budget = self.query_budget  # type: ignore[assignment]
            return await method(
                query=query,
                hl_keywords=hl_keywords,
                ll_keywords=ll_keywords,
                bounds=bounds,
            )

    async def retrieve_local(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Forward local graph retrieve.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads. Never evidence.
        """

        return await self._forward(
            "retrieve_local",
            query=query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )

    async def retrieve_hybrid(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Forward graph-hybrid retrieve.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Structured leads.
        """

        return await self._forward(
            "retrieve_hybrid",
            query=query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )

    async def retrieve_global_steering(
        self,
        *,
        query: str,
        hl_keywords: tuple[str, ...],
        ll_keywords: tuple[str, ...],
        bounds: object,
    ) -> object:
        """Forward global steering retrieve.

        Args:
            query: Original query.
            hl_keywords: Precomputed high-level keywords.
            ll_keywords: Precomputed low-level keywords.
            bounds: Adapter bounds.

        Returns:
            Steering leads. Never evidence.
        """

        return await self._forward(
            "retrieve_global_steering",
            query=query,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
            bounds=bounds,
        )


def _context_loader(
    supabase_dsn: str, caller: CallerContext
) -> Callable[[tuple[UUID, ...]], tuple[ChunkContext, ...]]:
    """Build a context RPC loader that opens one connection per fetch.

    Args:
        supabase_dsn: Canonical Postgres URL.
        caller: Retrieve caller captured for ACL.

    Returns:
        ``ContextFn`` used by ``HybridRetriever``.
    """

    def load(chunk_ids: tuple[UUID, ...]) -> tuple[ChunkContext, ...]:
        """Load authorized chunk context on a fresh idle login connection.

        ``fetch_authorized_chunk_context`` starts ``retrieval_transaction``,
        which requires an idle connection and applies ``SET LOCAL ROLE
        app_api``. Pre-setting the role would leave the connection
        in-transaction and fail closed on hosted pooler and local Postgres.

        Args:
            chunk_ids: Canonical IDs.

        Returns:
            Authorized rows. Unauthorized IDs are omitted.
        """

        with psycopg.connect(supabase_dsn) as connection:
            return fetch_authorized_chunk_context(
                connection,
                caller=caller,
                chunk_ids=chunk_ids,
            )

    return load


def bind_table_executor(postgres_url: str) -> TableExecuteLike:
    """Bind the existing structured-table engine with per-call ``app_api`` ACL.

    Args:
        postgres_url: Canonical Postgres URL.

    Returns:
        ``TableExecuteLike`` callable. Does not invent a second table engine.
    """

    def execute(spec: BranchSpec, caller: CallerContext) -> object:
        """Execute one table branch through ``structured_table_query``.

        Args:
            spec: Table branch spec with a declarative plan.
            caller: Server-derived caller.

        Returns:
            ``TableQueryResult``, or None when the plan is missing or ACL/sandbox
            refuses. Never a fabricated table success.
        """

        plan = spec.table_plan
        if plan is None:
            return None
        try:
            with psycopg.connect(postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                resolver = PostgresTableResolver(connection, local_root=Path("."))
                return structured_table_query(plan, caller=caller, resolver=resolver)
        except (
            TableResolveError,
            StructuredTableError,
            TableQueryRefusal,
            TableSandboxError,
            psycopg.Error,
            OSError,
        ):
            return None

    return execute


def _secret_url(value: object) -> str | None:
    """Return a DSN string from a settings secret or plain string.

    Args:
        value: ``SecretStr``, string, or None.

    Returns:
        Non-empty URL, or None.
    """

    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        raw = getter()
        if isinstance(raw, str) and raw:
            return raw
        return None
    if isinstance(value, str) and value:
        return value
    return None


def _lifespan_app_state() -> object | None:
    """Return process ``app.state`` after FastAPI lifespan when import-safe.

    Returns:
        ``app.state`` or None. Import is deferred to avoid a cycle with
        ``main`` which imports the SSE registry at module load.
    """

    try:
        from smart_rag_api.main import app as api_app
    except ImportError:
        return None
    return getattr(api_app, "state", None)


def build_query_process_bindings(
    *,
    settings: SharedSettings | None = None,
    app_state: object | None = None,
    supabase_dsn: str | None = None,
    model_gateway: object | None = None,
    lightrag_adapter: object | None = None,
    paradedb_url: str | None = None,
) -> QueryGraphProcessBindings:
    """Construct process-reusable Hybrid, gateway, table, and prompt bindings.

    Args:
        settings: Shared or backend settings. Loaded when omitted.
        app_state: Optional FastAPI ``app.state`` with lifespan adapters.
        supabase_dsn: Override canonical Postgres URL.
        model_gateway: Override gateway. Lifespan or ``create_model_gateway``
            is used when omitted.
        lightrag_adapter: Override graph retriever. Lifespan adapter is used
            when omitted. Missing adapter leaves graph unbound.
        paradedb_url: Override ``PARADEDB_URL``. Unset degrades BM25.

    Returns:
        Bindings with non-null Hybrid and model gateway.

    Raises:
        QueryGraphRuntimeError: When Hybrid or the gateway cannot be built.
    """

    loaded = settings if settings is not None else load_backend_settings()
    state = app_state if app_state is not None else _lifespan_app_state()
    dsn = supabase_dsn or _secret_url(getattr(loaded, "supabase_db_url", None))
    if not dsn:
        raise QueryGraphRuntimeError("hybrid_retriever_unbound")
    gateway = model_gateway
    if gateway is None and state is not None:
        gateway = getattr(state, "model_gateway", None)
    if gateway is None:
        try:
            gateway = create_model_gateway(loaded)
        except ModelGatewayUnavailableError as exc:
            raise QueryGraphRuntimeError("model_gateway_unbound") from exc
    if gateway is None:
        raise QueryGraphRuntimeError("model_gateway_unbound")
    graph = lightrag_adapter
    if graph is None and state is not None:
        graph = getattr(state, "lightrag_adapter", None)
    parade = paradedb_url or _secret_url(getattr(loaded, "paradedb_url", None))
    bm25 = DsnBm25Retriever(parade) if parade else None
    try:
        embedding = create_embedding_gateway(loaded)
    except ModelGatewayUnavailableError as exc:
        raise QueryGraphRuntimeError("hybrid_retriever_unbound") from exc
    hybrid = ProcessHybridRetriever(
        embedding_gateway=embedding,
        supabase_dsn=dsn,
        bm25=bm25,
    )
    graph_retriever: GraphRetrieveLike | None = None
    if graph is not None and all(
        hasattr(graph, name)
        for name in ("retrieve_local", "retrieve_hybrid", "retrieve_global_steering")
    ):
        graph_retriever = cast(GraphRetrieveLike, graph)
    return QueryGraphProcessBindings(
        hybrid_retriever=hybrid,
        model_gateway=gateway,
        graph_retriever=graph_retriever,
        table_executor=bind_table_executor(dsn),
        answer_prompt_text=answer_prompt_text(),
        verifier_prompt_text=verifier_prompt_text(),
        supabase_dsn=dsn,
    )


def build_query_graph_deps(
    *,
    bindings: QueryGraphProcessBindings,
    connection: psycopg.Connection | None,
    cancel_check: Callable[[], bool] | None,
    store_get: Callable[[tuple[str, str, str], str], dict[str, object] | None]
    | None = None,
    store_put: Callable[[tuple[str, str, str], str, dict[str, object]], None]
    | None = None,
) -> QueryGraphDeps:
    """Assemble per-run ``QueryGraphDeps`` from process bindings.

    Args:
        bindings: Process Hybrid/gateway/table/prompts.
        connection: Per-run ``app_api`` connection for memory and counted
            model calls. Must not be shared across concurrent runs.
        cancel_check: Per-run cooperative cancellation probe.
        store_get: Optional compact memory reader.
        store_put: Optional compact memory writer.

    Returns:
        Deps with non-null ``hybrid_retriever`` and ``model_gateway``.

    Raises:
        QueryGraphRuntimeError: If required adapters are missing.
    """

    if bindings.hybrid_retriever is None or bindings.model_gateway is None:
        raise QueryGraphRuntimeError("query_runtime_unbound")
    hybrid: HybridRetrieveLike
    if isinstance(bindings.hybrid_retriever, ProcessHybridRetriever):
        hybrid = _RunScopedHybrid(bindings.hybrid_retriever)
    else:
        hybrid = bindings.hybrid_retriever
    graph = (
        _RunScopedGraph(bindings.graph_retriever)
        if bindings.graph_retriever is not None
        else None
    )
    return QueryGraphDeps(
        connection=connection,
        hybrid_retriever=hybrid,
        graph_retriever=graph,
        table_executor=bindings.table_executor,
        cancel_check=cancel_check,
        answer_prompt_text=bindings.answer_prompt_text,
        verifier_prompt_text=bindings.verifier_prompt_text,
        model_gateway=bindings.model_gateway,
        store_get=store_get,
        store_put=store_put,
    )


def open_run_app_api_connection(supabase_dsn: str) -> psycopg.Connection:
    """Open one ``app_api`` connection for counted model calls on this run.

    Args:
        supabase_dsn: Canonical Postgres URL.

    Returns:
        Autocommit-off connection with ``SET ROLE app_api``.

    Raises:
        QueryGraphRuntimeError: If the connection cannot be opened.

    Side Effects:
        Opens a Postgres session. Caller must close it.
    """

    try:
        connection = psycopg.connect(supabase_dsn)
        connection.execute("SET ROLE app_api")
    except (psycopg.Error, OSError) as exc:
        raise QueryGraphRuntimeError("app_api_connection_unbound") from exc
    return connection
