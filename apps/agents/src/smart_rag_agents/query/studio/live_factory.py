"""Live Studio graph factory, open/close lifecycle, and compile helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import cast

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph_sdk.runtime import ServerRuntime
from smart_rag_core.observability.governance_gate import ExternalFlowBlockedError
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.jwks import JwksVerificationError
from smart_rag_core.settings.base import SettingsValidationError

from smart_rag_agents.query.graph import build_query_graph
from smart_rag_agents.query.live_runtime import (
    QueryGraphRuntimeError,
    build_query_graph_deps,
)
from smart_rag_agents.query.state import QueryGraphState
from smart_rag_agents.query.studio.input import StudioCompiledGraph, StudioQueryState
from smart_rag_agents.query.studio.live_admission import (
    DETAIL_GOVERNANCE,
    DETAIL_PROFILE,
    DETAIL_REVOKED,
    DETAIL_RUNTIME,
    DETAIL_TOKEN_INVALID,
    DETAIL_TOKEN_MISSING,
    bind_studio_live_seed,
    reject_studio_live,
)
from smart_rag_agents.query.studio.live_auth import (
    StudioLiveHooks,
    load_production_hooks,
)
from smart_rag_agents.query.studio.tracing import apply_studio_langsmith_flags

apply_studio_langsmith_flags()


def compile_live_graph(
    *,
    deps: object | None = None,
    seed: Callable[[StudioQueryState, RunnableConfig], QueryGraphState] | None = None,
) -> StudioCompiledGraph:
    """Compile one live Studio graph with the shared topology.

    Args:
        deps: Optional live bindings. ``None`` stays unbound.
        seed: Optional live seed. Default unbound seed rejects.

    Returns:
        Compiled Studio graph.
    """

    from smart_rag_agents.query.deps import QueryGraphDeps

    typed_deps = deps if isinstance(deps, QueryGraphDeps) else None
    return build_query_graph(  # pyright: ignore[reportUnknownMemberType, reportReturnType]
        typed_deps,
        studio_live=True,
        studio_live_seed=seed,
    ).compile()


@asynccontextmanager
async def open_studio_live_graph(
    runtime: ServerRuntime[None],
    *,
    hooks: StudioLiveHooks | None = None,
) -> AsyncGenerator[StudioCompiledGraph, None]:
    """Yield the live Studio graph, opening sockets only for execution.

    Args:
        runtime: Agent Server runtime. ``execution_runtime is None`` is
            introspection and opens zero sockets.
        hooks: Optional test hooks. Production loads settings when omitted.

    Yields:
        Compiled graph with the live Studio topology.

    Side Effects:
        Execution may open one ``app_api`` connection and process bindings.
        ``finally`` always closes that connection.
    """

    if runtime.execution_runtime is None:
        yield compile_live_graph()
        return

    try:
        resolved = hooks if hooks is not None else load_production_hooks()
    except (SettingsValidationError, ValueError, QueryGraphRuntimeError):
        yield compile_live_graph()
        return

    token = resolved.token_getter() if resolved.enabled else None
    if not resolved.enabled:
        yield compile_live_graph()
        return
    if token is None:
        yield compile_live_graph(
            seed=lambda state, config: reject_studio_live(state, DETAIL_TOKEN_MISSING)
        )
        return

    try:
        verified = resolved.verify_access_token(token)
    except JwksVerificationError:
        yield compile_live_graph(
            seed=lambda state, config: reject_studio_live(state, DETAIL_TOKEN_INVALID)
        )
        return

    snapshot = resolved.load_profile(verified.subject)
    if snapshot is None or snapshot.disabled:
        yield compile_live_graph(
            seed=lambda state, config: reject_studio_live(state, DETAIL_PROFILE)
        )
        return
    if resolved.is_revoked(verified, snapshot):
        yield compile_live_graph(
            seed=lambda state, config: reject_studio_live(state, DETAIL_REVOKED)
        )
        return
    try:
        resolved.assert_export_permitted()
    except ExternalFlowBlockedError:
        yield compile_live_graph(
            seed=lambda state, config: reject_studio_live(state, DETAIL_GOVERNANCE)
        )
        return

    connection: object | None = None
    try:
        connection = resolved.open_connection()

        def admit(**kwargs: object) -> object:
            """Admit with the captured per-run connection.

            Args:
                **kwargs: Seed admit fields.

            Returns:
                Authorized runtime context.
            """

            return resolved.admit(connection=connection, **kwargs)

        bound_hooks = StudioLiveHooks(
            enabled=True,
            token_getter=resolved.token_getter,
            verify_access_token=resolved.verify_access_token,
            load_profile=resolved.load_profile,
            is_revoked=resolved.is_revoked,
            admit=admit,
            assert_export_permitted=resolved.assert_export_permitted,
            open_connection=resolved.open_connection,
            build_bindings=resolved.build_bindings,
            postgres_url=resolved.postgres_url,
        )
        bindings = resolved.build_bindings()
        deps = build_query_graph_deps(
            bindings=bindings,
            connection=cast(psycopg.Connection, connection),
            cancel_check=None,
        )
        yield compile_live_graph(deps=deps, seed=bind_studio_live_seed(bound_hooks))
    except (QueryGraphRuntimeError, QueryAdmissionError, OSError):
        yield compile_live_graph(
            seed=lambda state, config: reject_studio_live(state, DETAIL_RUNTIME)
        )
    finally:
        closer = getattr(connection, "close", None)
        if callable(closer):
            closer()


@asynccontextmanager
async def make_graph(
    runtime: ServerRuntime[None],
) -> AsyncGenerator[StudioCompiledGraph, None]:
    """Agent Server graph factory for ``query_studio_live``.

    Signature matches pinned ``langgraph_api._factory_utils``: one
    ``ServerRuntime`` argument, async context manager returning the compiled
    graph. Introspection (``execution_runtime is None``) opens no sockets.

    Args:
        runtime: Agent Server runtime for this factory call.

    Yields:
        Compiled live Studio graph.
    """

    async with open_studio_live_graph(runtime) as compiled:
        yield compiled
