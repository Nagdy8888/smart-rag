"""Authenticated LangGraph Studio live adapter.

This graph is separate from unbound ``query_studio``. It admits a paid run
through core ``admit_query_run`` after JWKS verification and a live profile
reload. It never mints a synthetic ``studio_local`` context and never reads
a service-role key. The access token stays in a closure and is never written
to state, configurable, logs, checkpoints, or traces.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid5

import psycopg
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph_sdk.runtime import ServerRuntime
from smart_rag_core.observability.governance_gate import (
    ExternalFlowBlockedError,
    assert_langsmith_export_permitted,
)
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_admission.service import admit_query_run
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.external_processing import ContentClass
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.jwks import (
    JwksVerificationError,
    JwksVerifier,
    VerifiedAccessToken,
)
from smart_rag_core.security.profile_snapshot import (
    ProfileSnapshot,
    build_caller_context,
    is_session_revoked,
    load_profile_snapshot,
)
from smart_rag_core.settings import load_agent_settings, load_backend_settings
from smart_rag_core.settings.base import SettingsValidationError

from smart_rag_agents.query.graph import build_query_graph
from smart_rag_agents.query.live_runtime import (
    QueryGraphProcessBindings,
    QueryGraphRuntimeError,
    build_query_graph_deps,
    build_query_process_bindings,
    open_run_app_api_connection,
)
from smart_rag_agents.query.state import QueryGraphState, pending_query_state
from smart_rag_agents.query.studio import (
    StudioCompiledGraph,
    StudioQueryState,
    query_text_from_studio_input,
)
from smart_rag_agents.query.studio_tracing import apply_studio_langsmith_flags

apply_studio_langsmith_flags()

STUDIO_LIVE_NAMESPACE = UUID("c3e8a91b-6d2f-4e17-8a45-9b0c1d2e3f40")
"""Stable UUID namespace for live Studio conversation and idempotency keys."""

LIVE_ROUTE_FAMILY = Phase6RouteFamily.COMPOSITE
"""Same Auto envelope reserved by production FastAPI chat."""

QUERY_ADMISSION_RATE_MAX_ATTEMPTS = 20
QUERY_ADMISSION_RATE_WINDOW_SECONDS = 60

DETAIL_DISABLED = "studio live mode is disabled"
DETAIL_TOKEN_MISSING = "studio live access token is missing"  # noqa: S105
DETAIL_TOKEN_INVALID = "access token is invalid or expired"  # noqa: S105
DETAIL_REVOKED = "session is revoked"
DETAIL_PROFILE = "membership profile missing or disabled"
DETAIL_ADMISSION = "query admission was rejected"
DETAIL_GOVERNANCE = "langsmith export is not permitted"
DETAIL_RUNTIME = "studio live runtime is unavailable"

_STUDIO_LOCAL_STATUS = "studio_local"


@dataclass(slots=True)
class StudioLiveHooks:
    """Injectable live-Studio boundaries. The token is never stored here.

    Attributes:
        enabled: Whether authenticated live execution is allowed.
        token_getter: Returns the bearer JWT or ``None``. Never logged.
        verify_access_token: JWKS verification. Must not persist the token.
        load_profile: Live profile reload for the verified subject.
        is_revoked: Session revocation check.
        admit: Durable admit that returns a real authorized context.
        assert_export_permitted: LangSmith company-content gate.
        open_connection: Per-run ``app_api`` opener.
        build_bindings: Process Hybrid/gateway/table factory.
        postgres_url: Optional DSN for identity/revocation only.
    """

    enabled: bool
    token_getter: Callable[[], str | None]
    verify_access_token: Callable[[str], VerifiedAccessToken]
    load_profile: Callable[[str], ProfileSnapshot | None]
    is_revoked: Callable[[VerifiedAccessToken, ProfileSnapshot], bool]
    admit: Callable[..., object]
    assert_export_permitted: Callable[[], None]
    open_connection: Callable[[], object]
    build_bindings: Callable[[], QueryGraphProcessBindings]
    postgres_url: str | None = None


def studio_live_conversation_id(thread_id: str) -> UUID:
    """Return the stable conversation UUID for one Studio thread.

    Args:
        thread_id: LangGraph Studio thread identifier.

    Returns:
        ``uuid5`` under ``STUDIO_LIVE_NAMESPACE``. Not the local Studio
        synthetic namespace.
    """

    return uuid5(STUDIO_LIVE_NAMESPACE, thread_id)


def studio_live_idempotency_key(
    *,
    thread_id: str,
    turn_ref: str,
    payload_hash: str,
) -> UUID:
    """Return the durable idempotency key for one Studio live turn.

    Args:
        thread_id: Studio thread identifier.
        turn_ref: Last human message id, or the human-turn index.
        payload_hash: Canonical admit payload hash.

    Returns:
        ``uuid5`` of ``thread_id:turn_ref:payload_hash``.
    """

    return uuid5(STUDIO_LIVE_NAMESPACE, f"{thread_id}:{turn_ref}:{payload_hash}")


def _thread_id(config: RunnableConfig) -> str:
    """Return the Studio thread id, or ``studio-live``.

    Args:
        config: LangGraph runnable config.

    Returns:
        Non-empty thread identifier. Never an access token.
    """

    configurable = config.get("configurable")
    if isinstance(configurable, dict):
        raw = configurable.get("thread_id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "studio-live"


def _as_object_list(value: object) -> list[object]:
    """Return ``value`` as a list of objects.

    Args:
        value: Untrusted Studio payload fragment.

    Returns:
        A shallow copy typed as ``list[object]``.
    """

    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def last_human_turn_ref(state: object) -> str:
    """Return the last human message id, or the 1-based human-turn index.

    Args:
        state: Incoming Studio mapping.

    Returns:
        Stable turn reference used in the idempotency key. Empty when no
        human turn exists.
    """

    if not isinstance(state, dict):
        return "0"
    mapping = cast(dict[str, object], state)
    human_count = 0
    last_id = ""
    for item in _as_object_list(mapping.get("messages")):
        role = ""
        message_id = ""
        if isinstance(item, BaseMessage):
            role = item.type.lower()
            raw_id = getattr(item, "id", None)
            message_id = raw_id.strip() if isinstance(raw_id, str) else ""
        elif isinstance(item, dict):
            typed = cast(dict[str, object], item)
            role = str(typed.get("role") or typed.get("type") or "").lower()
            raw_id = typed.get("id")
            message_id = raw_id.strip() if isinstance(raw_id, str) else ""
        else:
            continue
        if role not in {"human", "user"}:
            continue
        human_count += 1
        last_id = message_id
    if last_id:
        return last_id
    return str(human_count)


def _reject(state: StudioQueryState, detail: str) -> QueryGraphState:
    """Return pending rejected state with one sanitized detail.

    Args:
        state: Incoming Studio mapping.
        detail: Safe operator-facing reason. Never a token or DSN.

    Returns:
        Pending state with ``admission_rejected`` and no authorized runtime.
    """

    query = query_text_from_studio_input(state)
    surface = state.get("routing_surface") or "production"
    requested: object = state.get("requested_manual_route")
    manual = requested if isinstance(requested, str) else None
    rejected = pending_query_state(
        user_query=query,
        routing_surface=surface,
        requested_manual_route=manual,
    )
    return {
        **rejected,
        "status": "admission_rejected",
        "detail": detail,
    }


def seed_studio_live_unbound(
    state: StudioQueryState,
    config: RunnableConfig,
) -> QueryGraphState:
    """Reject live Studio when the graph is unbound or disabled.

    State inputs:
        ``user_query`` / ``messages``. Token fields are ignored.

    State outputs:
        ``admission_rejected`` with no ``authorized_runtime``.

    Persistence writes:
        None.

    External/model calls:
        None. Opens no sockets.

    Budget/deadline behavior:
        None. Does not mint a synthetic envelope.

    Failure/fallback route:
        Always ``admission_rejected``. Status is never ``studio_local``.

    Args:
        state: Incoming Studio mapping.
        config: Runnable config. Unused.

    Returns:
        Rejected pending state.
    """

    _ = config
    return _reject(state, DETAIL_DISABLED)


def run_studio_live_seed(
    state: StudioQueryState,
    config: RunnableConfig,
    hooks: StudioLiveHooks,
) -> QueryGraphState:
    """Admit one Studio live turn through JWT, profile, and durable admit.

    State inputs:
        ``user_query`` / ``messages`` and optional routing fields.

    State outputs:
        Pending state with a real ``authorized_runtime``, or
        ``admission_rejected`` with a sanitized detail.

    Persistence writes:
        Rate-limit consume and ``admit_query_run`` when hooks admit.

    External/model calls:
        JWKS verify and profile reload. OpenAI and retrieval do not run here.

    Budget/deadline behavior:
        Reserves the Composite/Auto envelope via durable admit.

    Failure/fallback route:
        Disabled, missing, invalid, revoked, or admit failure reject without
        a ``studio_local`` context.

    Args:
        state: Incoming Studio mapping.
        config: Runnable config; ``configurable.thread_id`` names the
            conversation.
        hooks: Injectable auth/admit boundaries. Must not embed the token
            on the returned state.

    Returns:
        Pending query state with admitted context, or a rejected pending
        state.
    """

    if not hooks.enabled:
        return _reject(state, DETAIL_DISABLED)
    token = hooks.token_getter()
    if token is None or not token.strip():
        return _reject(state, DETAIL_TOKEN_MISSING)
    try:
        verified = hooks.verify_access_token(token)
    except JwksVerificationError:
        return _reject(state, DETAIL_TOKEN_INVALID)
    snapshot = hooks.load_profile(verified.subject)
    if snapshot is None or snapshot.disabled:
        return _reject(state, DETAIL_PROFILE)
    if hooks.is_revoked(verified, snapshot):
        return _reject(state, DETAIL_REVOKED)
    try:
        hooks.assert_export_permitted()
    except ExternalFlowBlockedError:
        return _reject(state, DETAIL_GOVERNANCE)
    query = query_text_from_studio_input(state)
    thread_id = _thread_id(config)
    conversation_id = studio_live_conversation_id(thread_id)
    payload_hash = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=LIVE_ROUTE_FAMILY,
        message=query,
    )
    idempotency_key = studio_live_idempotency_key(
        thread_id=thread_id,
        turn_ref=last_human_turn_ref(state),
        payload_hash=payload_hash,
    )
    caller = build_caller_context(
        snapshot,
        session_id=verified.session_id,
        assurance_level=verified.assurance_level,
        authentication_methods=verified.authentication_methods,
    )
    issued_at = (
        datetime.fromtimestamp(verified.issued_at, tz=UTC)
        if verified.issued_at is not None
        else None
    )
    try:
        admitted = hooks.admit(
            caller=caller,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            message=query,
            token_issued_at=issued_at,
        )
    except QueryAdmissionError:
        return _reject(state, DETAIL_ADMISSION)
    if not isinstance(admitted, AuthorizedRuntimeContext):
        return _reject(state, DETAIL_ADMISSION)
    if admitted.status == _STUDIO_LOCAL_STATUS:
        return _reject(state, DETAIL_ADMISSION)
    dumped = cast(dict[str, object], admitted.model_dump(mode="json"))
    surface = state.get("routing_surface") or "production"
    requested: object = state.get("requested_manual_route")
    manual = requested if isinstance(requested, str) else None
    return pending_query_state(
        dumped,
        user_query=query,
        routing_surface=surface,
        requested_manual_route=manual,
    )


def bind_studio_live_seed(hooks: StudioLiveHooks) -> Callable[
    [StudioQueryState, RunnableConfig],
    QueryGraphState,
]:
    """Return a LangGraph seed node that captures hooks, not the token.

    Args:
        hooks: Auth and admit boundaries.

    Returns:
        Node function named ``seed_studio_live_runtime``.
    """

    def seed_studio_live_runtime(
        state: StudioQueryState,
        config: RunnableConfig,
    ) -> QueryGraphState:
        """Admit the current Studio live turn.

        Args:
            state: Incoming Studio mapping.
            config: Runnable config.

        Returns:
            Pending admitted or rejected state.
        """

        return run_studio_live_seed(state, config, hooks)

    return seed_studio_live_runtime


def _secret_text(value: object) -> str | None:
    """Return a secret string without logging it.

    Args:
        value: ``SecretStr`` or ``None``.

    Returns:
        Plaintext secret, or ``None``.
    """

    if value is None:
        return None
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        raw = getter()
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _consume_rate_limit(connection: psycopg.Connection, *, user_id: str) -> None:
    """Consume the same query-admission Postgres bucket used by FastAPI.

    Args:
        connection: Open ``app_api`` connection.
        user_id: Verified subject.

    Raises:
        QueryAdmissionError: ``rate_limited`` or ``limiter_unavailable``.
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT private.consume_auth_rate_limit(%s, %s, %s)
                """,
                (
                    f"query-admission:{user_id}",
                    QUERY_ADMISSION_RATE_MAX_ATTEMPTS,
                    QUERY_ADMISSION_RATE_WINDOW_SECONDS,
                ),
            )
            row = cursor.fetchone()
    except QueryAdmissionError:
        raise
    except Exception as exc:
        raise QueryAdmissionError("limiter_unavailable") from exc
    if row is None or not bool(row[0]):
        raise QueryAdmissionError("rate_limited")


def production_admit(
    *,
    connection: psycopg.Connection,
    caller: CallerContext,
    conversation_id: UUID,
    idempotency_key: UUID,
    payload_hash: str,
    message: str,
    token_issued_at: datetime | None,
) -> object:
    """Rate-limit then admit through the durable RPC on the per-run connection.

    Args:
        connection: Open ``app_api`` connection. Caller commits on success.
        caller: JWKS-verified, profile-reloaded identity.
        conversation_id: Stable Studio live conversation UUID.
        idempotency_key: Turn idempotency key.
        payload_hash: Canonical payload hash.
        message: User text hashed into the payload. Unused by SQL except
            through ``payload_hash``.
        token_issued_at: JWT ``iat``.

    Returns:
        ``AuthorizedRuntimeContext`` from durable admit.

    Raises:
        QueryAdmissionError: Rate, limiter, or RPC failure.
    """

    _ = message
    _consume_rate_limit(connection, user_id=caller.user_id)
    result = admit_query_run(
        connection,
        caller=caller,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        route_family=LIVE_ROUTE_FAMILY,
        token_issued_at=token_issued_at,
    )
    commit = getattr(connection, "commit", None)
    if callable(commit):
        commit()
    return result.context


def load_production_hooks() -> StudioLiveHooks:
    """Build live hooks from ``AgentSettings`` plus separate ``BackendSettings``.

    Returns:
        Hooks that verify JWT, reload profile, and admit. The token is read
        through a getter and never assigned to a hook field.

    Raises:
        SettingsValidationError: When agent or backend settings are invalid.
        QueryGraphRuntimeError: When the identity DSN is missing.
    """

    agent = load_agent_settings()
    backend = load_backend_settings()
    token = _secret_text(agent.langgraph_studio_access_token)
    dsn = _secret_text(getattr(backend, "supabase_db_url", None))
    supabase_url = str(backend.supabase_url)

    def token_getter() -> str | None:
        """Return the configured access token.

        Returns:
            Bearer JWT, or ``None``.
        """

        return token

    def verify_access_token(raw_token: str) -> VerifiedAccessToken:
        """Verify the bearer JWT against hosted JWKS.

        Args:
            raw_token: Access token. Never logged.

        Returns:
            Verified claims.

        Raises:
            JwksVerificationError: Signature, audience, issuer, or expiry.
        """

        verifier = JwksVerifier(
            supabase_url=supabase_url,
            audience=backend.supabase_jwt_audience,
            cache_seconds=backend.jwks_cache_seconds,
            app_env=backend.app_env.value,
        )
        return verifier.verify_access_token(raw_token)

    def load_profile(user_id: str) -> ProfileSnapshot | None:
        """Reload the authoritative profile.

        Args:
            user_id: Verified subject.

        Returns:
            Snapshot, or ``None`` when missing.
        """

        if dsn is None:
            return None
        return load_profile_snapshot(dsn, user_id=user_id)

    def revoked(verified: VerifiedAccessToken, snapshot: ProfileSnapshot) -> bool:
        """Return whether the session is revoked.

        Args:
            verified: Verified token claims.
            snapshot: Live profile.

        Returns:
            ``True`` when the session must be rejected.
        """

        if dsn is None:
            return True
        return is_session_revoked(
            dsn,
            session_id=verified.session_id,
            issued_at=verified.issued_at,
            session_revoked_at=snapshot.session_revoked_at,
        )

    def export_gate() -> None:
        """Block company-content LangSmith export when unverified.

        Raises:
            ExternalFlowBlockedError: When tracing would leak company text.
        """

        assert_langsmith_export_permitted(
            tracing_enabled=agent.langsmith_tracing,
            content_class=ContentClass.REAL_COMPANY,
            provider_settings_verified=agent.subprocessor_matrix_verified,
            local_unsigned_waiver=agent.allows_unsigned_local_live_providers(),
        )

    def open_connection() -> object:
        """Open the per-run ``app_api`` connection.

        Returns:
            Open connection.

        Raises:
            QueryGraphRuntimeError: When the DSN is missing or connect fails.
        """

        if dsn is None:
            raise QueryGraphRuntimeError("app_api_connection_unbound")
        return open_run_app_api_connection(dsn)

    def bindings() -> QueryGraphProcessBindings:
        """Build process Hybrid/gateway/table bindings.

        Returns:
            Process bindings. Does not import FastAPI.
        """

        return build_query_process_bindings(settings=backend, app_state=None)

    def admit(**kwargs: object) -> object:
        """Admit using the connection captured later by the factory.

        Args:
            **kwargs: Admit fields plus optional ``connection``.

        Returns:
            Authorized runtime context.

        Raises:
            QueryAdmissionError: When admit cannot run.
        """

        connection = kwargs.get("connection")
        if not isinstance(connection, psycopg.Connection):
            raise QueryAdmissionError("database_rejected")
        return production_admit(
            connection=connection,  # pyright: ignore[reportUnknownArgumentType]
            caller=cast(CallerContext, kwargs["caller"]),
            conversation_id=cast(UUID, kwargs["conversation_id"]),
            idempotency_key=cast(UUID, kwargs["idempotency_key"]),
            payload_hash=cast(str, kwargs["payload_hash"]),
            message=cast(str, kwargs["message"]),
            token_issued_at=cast(datetime | None, kwargs.get("token_issued_at")),
        )

    return StudioLiveHooks(
        enabled=agent.langgraph_studio_live_enabled,
        token_getter=token_getter,
        verify_access_token=verify_access_token,
        load_profile=load_profile,
        is_revoked=revoked,
        admit=admit,
        assert_export_permitted=export_gate,
        open_connection=open_connection,
        build_bindings=bindings,
        postgres_url=None,
    )


def _compile_live_graph(
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
        yield _compile_live_graph()
        return

    try:
        resolved = hooks if hooks is not None else load_production_hooks()
    except (SettingsValidationError, ValueError, QueryGraphRuntimeError):
        yield _compile_live_graph()
        return

    token = resolved.token_getter() if resolved.enabled else None
    if not resolved.enabled:
        yield _compile_live_graph()
        return
    if token is None:
        yield _compile_live_graph(seed=lambda state, config: _reject(state, DETAIL_TOKEN_MISSING))
        return

    try:
        verified = resolved.verify_access_token(token)
    except JwksVerificationError:
        yield _compile_live_graph(seed=lambda state, config: _reject(state, DETAIL_TOKEN_INVALID))
        return

    snapshot = resolved.load_profile(verified.subject)
    if snapshot is None or snapshot.disabled:
        yield _compile_live_graph(seed=lambda state, config: _reject(state, DETAIL_PROFILE))
        return
    if resolved.is_revoked(verified, snapshot):
        yield _compile_live_graph(seed=lambda state, config: _reject(state, DETAIL_REVOKED))
        return
    try:
        resolved.assert_export_permitted()
    except ExternalFlowBlockedError:
        yield _compile_live_graph(seed=lambda state, config: _reject(state, DETAIL_GOVERNANCE))
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
        yield _compile_live_graph(deps=deps, seed=bind_studio_live_seed(bound_hooks))
    except (QueryGraphRuntimeError, QueryAdmissionError, OSError):
        yield _compile_live_graph(seed=lambda state, config: _reject(state, DETAIL_RUNTIME))
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
