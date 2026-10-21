"""Optional runtime bindings for the query graph. Import constructs no clients."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

import psycopg
from smart_rag_core.query_profile.versions import PROFILE_MODEL_ID
from smart_rag_core.query_routing.branches import (
    GraphRetrieveLike,
    HybridRetrieveLike,
    TableExecuteLike,
)
from smart_rag_core.query_routing.preparation import PrepModelCaller
from smart_rag_core.security.identity import UserRole
from smart_rag_core.tools.compare import RUNTIME_SELECTION_POLICY
from smart_rag_core.tools.models import SelectionPolicy


@dataclass(slots=True)
class QueryGraphDeps:
    """Injectable adapters for memory, prep, retrieve, and optional tools.

    All fields default so Studio ``graph.py`` can compile without sockets
    or OpenAI clients. Live FastAPI SSE and ``query_studio_live`` bind
    Hybrid, gateway, prompts, and a per-run ``app_api`` connection via
    ``smart_rag_agents.query.live_runtime``. Do not share
    ``cancel_check`` or ``connection`` across concurrent compiled graphs.

    Attributes:
        connection: ``app_api`` connection for memory load and counted prep.
        hybrid_retriever: Direct Hybrid retrieve adapter.
        graph_retriever: Direct GraphRetriever adapter.
        table_executor: Direct structured-table adapter.
        model_caller: One structured rewrite-plus-profile adapter.
        force_model: Spend the one prep call even when deterministic.
        cancel_check: Cooperative cancellation probe.
        query_profile_prompt_text: Pinned ``query_profile_v1`` body when a
            live or mock profile adapter runs.
        profile_model_id: Provider model id recorded on profile usage.
        answer_prompt_text: Pinned ``answer_v2`` body when a live adapter runs.
        organize_prompt_text: Deprecated compatibility field; never used to rewrite.
        general_chat_prompt_text: Pinned ``general_chat_v1`` body when a live
            general-chat adapter runs.
        verifier_prompt_text: Pinned ``verifier_v1`` body when a live adapter runs.
        web_critique_prompt_text: Pinned ``web_critique_v1`` body. Critique
            itself is deterministic; the file pins the live-model contract.
        web_answer_prompt_text: Pinned ``web_answer_v1`` body. Synthesis uses
            the budgeted model gateway when bound, otherwise extractive mock.
        model_gateway: Optional ``ModelGateway``. Compile constructs none.
        optional_policy: Frozen mapping-versus-discovery policy.
        force_discovery: Test hook for the one catalog round.
        chat_model: Optional langchain-core chat model for next-call bind.
        live_role_override: Test hook for role-change-after-plan.
        last_bound_runnable: Last next-call bind, for contract tests.
        unbound_model: Original model after bind, for unbind proofs.
        store_get: Optional LangGraph store reader for compact summaries.
        store_put: Optional LangGraph store writer for compact summaries.
        web_search_enabled: ``WEB_SEARCH_ENABLED`` snapshot for fail-closed
            Web routing. Default false.
        web_search_configured: True when a non-empty Exa key is present.
        exa_search_gateway: Injected Exa REST client, or None.
        crawl_proxy_gateway: Injected crawl-proxy client, or None.
        model_input_max_chars: Existing ``MODEL_INPUT_MAX_CHARS`` bound used
            when fitting company source records. Never raised by fitting.
        now: Optional UTC clock for answer-stage deadline tests.
    """

    connection: psycopg.Connection | None = None
    hybrid_retriever: HybridRetrieveLike | None = None
    graph_retriever: GraphRetrieveLike | None = None
    table_executor: TableExecuteLike | None = None
    model_caller: PrepModelCaller | None = None
    force_model: bool = False
    cancel_check: Callable[[], bool] | None = None
    query_profile_prompt_text: str | None = None
    profile_model_id: str = PROFILE_MODEL_ID
    answer_prompt_text: str | None = None
    organize_prompt_text: str | None = None
    general_chat_prompt_text: str | None = None
    verifier_prompt_text: str | None = None
    web_critique_prompt_text: str | None = None
    web_answer_prompt_text: str | None = None
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
    web_search_enabled: bool = False
    web_search_configured: bool = False
    exa_search_gateway: object | None = None
    crawl_proxy_gateway: object | None = None
    model_input_max_chars: int = 32_768
    now: Callable[[], datetime] | None = None


@dataclass(slots=True)
class QueryGraphContext:
    """Per-invocation LangGraph runtime context. Never compiled into topology.

    Attributes:
        deps: Run-local adapters, connection, and cancellation probe.
    """

    deps: QueryGraphDeps


_QUERY_RUN_DEPS: ContextVar[QueryGraphDeps | None] = ContextVar(
    "smart_rag_query_run_deps", default=None
)


def bind_query_run_deps(deps: QueryGraphDeps) -> Token[QueryGraphDeps | None]:
    """Bind per-run deps onto this task for LangGraph worker threads.

    LangGraph ``astream`` runs sync nodes through ``run_in_executor``.
    ``Runtime.context`` is the primary injection path. This contextvar is
    the fail-closed fallback when a tick restores a Runtime without
    ``QueryGraphDeps``.

    Args:
        deps: Run-local adapters for the active SSE stream.

    Returns:
        Token that ``reset_query_run_deps`` must consume.

    Side Effects:
        Sets a task-local ContextVar. Does not log secrets or DSNs.
    """

    return _QUERY_RUN_DEPS.set(deps)


def reset_query_run_deps(token: Token[QueryGraphDeps | None]) -> None:
    """Restore the previous per-run deps binding.

    Args:
        token: Value returned by ``bind_query_run_deps``.
    """

    _QUERY_RUN_DEPS.reset(token)


def _deps_from_context(context: object) -> QueryGraphDeps | None:
    """Return ``QueryGraphDeps`` from a Runtime context object or mapping.

    Args:
        context: ``QueryGraphContext``, a mapping with ``deps``, or any
            object with a ``deps`` attribute.

    Returns:
        Run deps when the value is a ``QueryGraphDeps`` instance.
    """

    if isinstance(context, QueryGraphContext):
        return context.deps
    if isinstance(context, Mapping):
        typed_context = cast(Mapping[str, object], context)
        deps = typed_context.get("deps")
        return deps if isinstance(deps, QueryGraphDeps) else None
    deps = getattr(context, "deps", None)
    return deps if isinstance(deps, QueryGraphDeps) else None


def deps_from_runtime(runtime: object, fallback: QueryGraphDeps) -> QueryGraphDeps:
    """Read run-scoped deps from LangGraph ``Runtime.context``.

    Args:
        runtime: Injected ``langgraph.runtime.Runtime``, a mapping with
            ``context``, or any object with an optional ``context.deps``
            attribute.
        fallback: Topology-compile default. Must be empty for a process
            cache; tests may pass bound deps when they invoke without
            ``context=``.

    Returns:
        The invocation's ``QueryGraphDeps`` when present, otherwise the
        task-local binding, otherwise ``fallback``. Never a prior run's
        compiled-graph capture.
    """

    context = getattr(runtime, "context", None)
    if context is None and isinstance(runtime, Mapping):
        typed_runtime = cast(Mapping[str, object], runtime)
        context = typed_runtime.get("context")
        if context is None:
            configurable = typed_runtime.get("configurable")
            if isinstance(configurable, Mapping):
                typed_configurable = cast(Mapping[str, object], configurable)
                context = typed_configurable.get("context")
    found = _deps_from_context(context) if context is not None else None
    if found is not None:
        return found
    try:
        from langgraph.runtime import get_runtime

        injected = get_runtime(QueryGraphContext)
        found = _deps_from_context(getattr(injected, "context", None))
        if found is not None:
            return found
    except (RuntimeError, LookupError, AttributeError, TypeError, KeyError):
        pass
    current = _QUERY_RUN_DEPS.get()
    if isinstance(current, QueryGraphDeps):
        return current
    return fallback
