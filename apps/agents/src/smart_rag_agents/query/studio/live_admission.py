"""Idempotency, rate-limit, and durable admit for live Studio."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid5

import psycopg
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from smart_rag_core.observability.governance_gate import ExternalFlowBlockedError
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_admission.service import admit_query_run
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.search_scope import RequestedSearchScope
from smart_rag_core.security.jwks import JwksVerificationError
from smart_rag_core.security.profile_snapshot import build_caller_context

from smart_rag_agents.query.state import QueryGraphState, pending_query_state
from smart_rag_agents.query.studio.input import (
    StudioQueryState,
    as_object_list,
    query_text_from_studio_input,
    studio_thread_id,
)

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
    for item in as_object_list(mapping.get("messages")):
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


def reject_studio_live(state: StudioQueryState, detail: str) -> QueryGraphState:
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
    return reject_studio_live(state, DETAIL_DISABLED)


def run_studio_live_seed(
    state: StudioQueryState,
    config: RunnableConfig,
    hooks: object,
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

    from smart_rag_agents.query.studio.live_auth import StudioLiveHooks

    typed = hooks if isinstance(hooks, StudioLiveHooks) else None
    if typed is None or not typed.enabled:
        return reject_studio_live(state, DETAIL_DISABLED)
    token = typed.token_getter()
    if token is None or not token.strip():
        return reject_studio_live(state, DETAIL_TOKEN_MISSING)
    try:
        verified = typed.verify_access_token(token)
    except JwksVerificationError:
        return reject_studio_live(state, DETAIL_TOKEN_INVALID)
    snapshot = typed.load_profile(verified.subject)
    if snapshot is None or snapshot.disabled:
        return reject_studio_live(state, DETAIL_PROFILE)
    if typed.is_revoked(verified, snapshot):
        return reject_studio_live(state, DETAIL_REVOKED)
    try:
        typed.assert_export_permitted()
    except ExternalFlowBlockedError:
        return reject_studio_live(state, DETAIL_GOVERNANCE)
    query = query_text_from_studio_input(state)
    thread_id = studio_thread_id(config, default="studio-live")
    conversation_id = studio_live_conversation_id(thread_id)
    payload_hash = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=LIVE_ROUTE_FAMILY,
        message=query,
        requested_search_scope=RequestedSearchScope.AUTO,
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
        admitted = typed.admit(
            caller=caller,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            message=query,
            token_issued_at=issued_at,
        )
    except QueryAdmissionError:
        return reject_studio_live(state, DETAIL_ADMISSION)
    if not isinstance(admitted, AuthorizedRuntimeContext):
        return reject_studio_live(state, DETAIL_ADMISSION)
    if admitted.status == _STUDIO_LOCAL_STATUS:
        return reject_studio_live(state, DETAIL_ADMISSION)
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


def bind_studio_live_seed(
    hooks: object,
) -> Callable[
    [StudioQueryState, RunnableConfig],
    QueryGraphState,
]:
    """Return a LangGraph seed node that captures hooks, not the token.

    Args:
        hooks: Auth and admit boundaries.

    Returns:
        Seed callable for ``build_query_graph(studio_live=True)``.
    """

    def seed_studio_live_runtime(
        state: StudioQueryState, config: RunnableConfig
    ) -> QueryGraphState:
        """Bound seed that never writes the token into state.

        Args:
            state: Incoming Studio mapping.
            config: Runnable config.

        Returns:
            Admitted or rejected pending state.
        """

        return run_studio_live_seed(state, config, hooks)

    return seed_studio_live_runtime


def consume_rate_limit(connection: psycopg.Connection, *, user_id: str) -> None:
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
    caller: object,
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

    from smart_rag_core.security.identity import CallerContext

    _ = message
    typed_caller = cast(CallerContext, caller)
    consume_rate_limit(connection, user_id=typed_caller.user_id)
    result = admit_query_run(
        connection,
        caller=typed_caller,
        conversation_id=conversation_id,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        route_family=LIVE_ROUTE_FAMILY,
        requested_search_scope=RequestedSearchScope.AUTO,
        token_issued_at=token_issued_at,
    )
    commit = getattr(connection, "commit", None)
    if callable(commit):
        commit()
    return result.context
