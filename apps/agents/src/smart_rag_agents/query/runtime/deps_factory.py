"""Run-scoped query-graph dependency factories."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import psycopg
from pydantic import SecretStr
from smart_rag_core.gateways.crawl_proxy import CrawlProxyGateway
from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.gateways.exa_search import (
    ExaSearchError,
    ExaSearchGateway,
    create_exa_search_gateway,
)
from smart_rag_core.gateways.model import (
    ModelGatewayUnavailableError,
    create_model_gateway,
)
from smart_rag_core.query_profile.versions import PROFILE_MODEL_ID
from smart_rag_core.query_routing.branches import (
    GraphRetrieveLike,
    HybridRetrieveLike,
)
from smart_rag_core.retrieval.cache_store import RetrievalCacheStore
from smart_rag_core.runtime.valkey import ValkeyClient
from smart_rag_core.settings import SharedSettings, load_backend_settings
from smart_rag_core.settings.postgres_connect import connect_postgres

from smart_rag_agents.prompts import (
    answer_prompt_text,
    general_chat_prompt_text,
    query_profile_prompt_text,
    rerank_prompt_text,
    verifier_prompt_text,
    web_answer_prompt_text,
    web_critique_prompt_text,
)
from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.runtime.adapters import (
    DsnBm25Retriever,
    ProcessHybridRetriever,
    RunScopedGraph,
    RunScopedHybrid,
    bind_profile_model_caller,
    bind_table_executor,
)
from smart_rag_agents.query.runtime.bindings import (
    QueryGraphProcessBindings,
    QueryGraphRuntimeError,
)


def secret_url(value: object) -> str | None:
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


def _web_gateway_stale(gateway: object, settings: object) -> bool:
    """Return whether the cached Exa gateway cannot serve this Ask.

    Args:
        gateway: Current deps gateway.
        settings: Process settings for this run.

    Returns:
        True when the gateway is missing, the wrong type, closed, or
        bound to a different key.
    """

    if not isinstance(gateway, ExaSearchGateway):
        return True
    if gateway.closed:
        return True
    key = getattr(settings, "exa_api_key", None)
    if not isinstance(key, SecretStr):
        return True
    return not gateway.credential_matches(key)


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
        app_state: Optional process adapters (FastAPI ``app.state``). This
            function never imports FastAPI to discover state.
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
    state = app_state
    dsn = supabase_dsn or secret_url(getattr(loaded, "supabase_db_url", None))
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
    parade = paradedb_url or secret_url(getattr(loaded, "paradedb_url", None))
    bm25 = DsnBm25Retriever(parade) if parade else None
    cache_store: RetrievalCacheStore | None = None
    if state is not None:
        cache_client = getattr(state, "valkey_cache_client", None)
        if cache_client is not None:
            cache_store = RetrievalCacheStore(cast(ValkeyClient, cache_client))
    try:
        embedding = create_embedding_gateway(loaded)
    except ModelGatewayUnavailableError as exc:
        raise QueryGraphRuntimeError("hybrid_retriever_unbound") from exc
    hybrid = ProcessHybridRetriever(
        embedding_gateway=embedding,
        supabase_dsn=dsn,
        bm25=bm25,
        model_gateway=gateway,  # type: ignore[arg-type]
        rerank_prompt_text=rerank_prompt_text(),
        retrieval_cache=cache_store,
    )
    graph_retriever: GraphRetrieveLike | None = None
    if graph is not None and all(
        hasattr(graph, name)
        for name in ("retrieve_local", "retrieve_hybrid", "retrieve_global_steering")
    ):
        graph_retriever = cast(GraphRetrieveLike, graph)
    exa_gateway = None
    if bool(getattr(loaded, "web_search_enabled", False)):
        try:
            exa_gateway = create_exa_search_gateway(loaded)
        except ExaSearchError:
            exa_gateway = None
    crawl_gateway = None
    proxy_url = getattr(loaded, "crawl_proxy_url", None)
    if proxy_url is not None:
        crawl_gateway = CrawlProxyGateway(proxy_base_url=str(proxy_url))
    return QueryGraphProcessBindings(
        hybrid_retriever=hybrid,  # pyright: ignore[reportArgumentType]
        model_gateway=gateway,
        graph_retriever=graph_retriever,
        table_executor=bind_table_executor(dsn),
        answer_prompt_text=answer_prompt_text(),
        general_chat_prompt_text=general_chat_prompt_text(),
        verifier_prompt_text=verifier_prompt_text(),
        query_profile_prompt_text=query_profile_prompt_text(),
        profile_model_id=PROFILE_MODEL_ID,
        supabase_dsn=dsn,
        web_search_enabled=bool(getattr(loaded, "web_search_enabled", False)),
        web_search_configured=secret_url(getattr(loaded, "exa_api_key", None))
        is not None,
        exa_search_gateway=exa_gateway,
        crawl_proxy_gateway=crawl_gateway,
        web_critique_prompt_text=web_critique_prompt_text(),
        web_answer_prompt_text=web_answer_prompt_text(),
        model_input_max_chars=int(getattr(loaded, "model_input_max_chars", 16_384)),
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

    if bindings.hybrid_retriever is None or bindings.model_gateway is None:  # pyright: ignore[reportUnnecessaryComparison]
        raise QueryGraphRuntimeError("query_runtime_unbound")
    hybrid: HybridRetrieveLike
    if isinstance(bindings.hybrid_retriever, ProcessHybridRetriever):
        hybrid = RunScopedHybrid(bindings.hybrid_retriever)  # pyright: ignore[reportAssignmentType]
    else:
        hybrid = bindings.hybrid_retriever
    graph = (
        RunScopedGraph(bindings.graph_retriever)
        if bindings.graph_retriever is not None
        else None
    )
    return QueryGraphDeps(
        connection=connection,
        hybrid_retriever=hybrid,
        graph_retriever=graph,  # pyright: ignore[reportArgumentType]
        table_executor=bindings.table_executor,
        cancel_check=cancel_check,
        model_caller=bind_profile_model_caller(
            gateway=bindings.model_gateway,
            prompt_text=bindings.query_profile_prompt_text,
            model_id=bindings.profile_model_id,
            cancel_check=cancel_check,
        ),
        query_profile_prompt_text=bindings.query_profile_prompt_text,
        profile_model_id=bindings.profile_model_id,
        answer_prompt_text=bindings.answer_prompt_text,
        general_chat_prompt_text=bindings.general_chat_prompt_text,
        verifier_prompt_text=bindings.verifier_prompt_text,
        web_critique_prompt_text=bindings.web_critique_prompt_text or None,
        web_answer_prompt_text=bindings.web_answer_prompt_text or None,
        model_gateway=bindings.model_gateway,
        store_get=store_get,
        store_put=store_put,
        web_search_enabled=bindings.web_search_enabled,
        web_search_configured=bindings.web_search_configured,
        exa_search_gateway=bindings.exa_search_gateway,
        crawl_proxy_gateway=bindings.crawl_proxy_gateway,
        model_input_max_chars=bindings.model_input_max_chars,
    )


def refresh_web_search_deps(deps: QueryGraphDeps, settings: object) -> QueryGraphDeps:
    """Copy current process Web flags onto run deps.

    Process Hybrid bindings are cached for the API lifetime. Compose
    ``env_file`` snapshots can leave that cache with ``web_search_enabled``
    false after the operator enables public Exa. Per-run assembly must
    reread ``WEB_SEARCH_ENABLED`` / ``EXA_API_KEY`` from the settings
    object used for this Ask.

    Args:
        deps: Mutable per-run adapters. Not frozen.
        settings: Backend or shared settings for this process.

    Returns:
        The same ``deps`` instance with Web flags and gateway refreshed.

    Side Effects:
        May construct an ``ExaSearchGateway`` bound to ``https://api.exa.ai``
        when the cached gateway is missing, the wrong type, closed, or
        bound to a different key. Never logs the key.
    """

    enabled = bool(getattr(settings, "web_search_enabled", False))
    configured = secret_url(getattr(settings, "exa_api_key", None)) is not None
    gateway = deps.exa_search_gateway
    if not enabled:
        gateway = None
    elif _web_gateway_stale(gateway, settings):
        try:
            if isinstance(settings, SharedSettings):
                gateway = create_exa_search_gateway(settings)
            else:
                gateway = None
        except ExaSearchError:
            gateway = None
    deps.web_search_enabled = enabled
    deps.web_search_configured = configured
    deps.exa_search_gateway = gateway
    return deps


def open_run_app_api_connection(supabase_dsn: str) -> psycopg.Connection:
    """Open one ``app_api`` connection for counted model calls on this run.

    Args:
        supabase_dsn: Canonical Postgres URL.

    Returns:
        Autocommit-off connection with ``SET ROLE app_api``.

    Raises:
        QueryGraphRuntimeError: If the connection cannot be opened.

    Side Effects:
        Opens a Postgres session with automatic prepares disabled so
        hosted transaction poolers cannot raise
        ``DuplicatePreparedStatement``. Caller must close it.
    """

    try:
        connection = connect_postgres(supabase_dsn)
        connection.execute("SET ROLE app_api")
    except (psycopg.Error, OSError) as exc:
        raise QueryGraphRuntimeError("app_api_connection_unbound") from exc
    return connection
