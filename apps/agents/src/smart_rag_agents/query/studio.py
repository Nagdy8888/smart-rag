"""Local LangGraph Studio adapter for the query graph.

This module is a developer surface. It does not admit a paid query run, open
Postgres, or replace FastAPI ``admit_query_run``. The seeded
``AuthorizedRuntimeContext`` is synthetic so Studio can invoke the same nodes
with ``{"user_query": "..."}``.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import TypeAlias, cast
from uuid import UUID, uuid4, uuid5

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from smart_rag_core.query_admission.ceilings import envelope_for_family
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import UserRole
from typing_extensions import TypedDict

from smart_rag_agents.query.graph import build_query_graph
from smart_rag_agents.query.state import QueryGraphState, pending_query_state

STUDIO_NAMESPACE = UUID("8f1c0d2a-4b7e-4c9a-9d31-7a6e5f4b3c21")
"""Stable UUID namespace for Studio conversation/user ids. Not an auth subject."""

_STUDIO_PAYLOAD_PREFIX = "langgraph-studio-local:"


class StudioQueryInput(TypedDict, total=False):
    """Minimal Studio input. Not a production admit payload.

    Attributes:
        user_query: Original user text. Untrusted.
        route_family: Optional Phase 6 family. Defaults to ``hybrid``.
        routing_surface: ``production`` or ``diagnostic``.
        requested_manual_route: Diagnostic-only route string.
        messages: Optional Studio chat messages; last human text is used when
            ``user_query`` is empty.
    """

    user_query: str
    route_family: str
    routing_surface: str
    requested_manual_route: str | None
    messages: list[dict[str, object]]


StudioCompiledGraph: TypeAlias = CompiledStateGraph[
    QueryGraphState,
    None,
    StudioQueryInput,
    QueryGraphState,
]


def _as_object_list(value: object) -> list[object]:
    """Return ``value`` as a list of objects, or empty when it is not a list.

    Args:
        value: Untrusted Studio payload fragment.

    Returns:
        A shallow copy typed as ``list[object]``.
    """

    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def _text_from_message_content(content: object) -> str:
    """Return plain text from a Studio/LangChain message content field.

    Args:
        content: String or list of text-part mappings.

    Returns:
        Stripped text, or empty when no string payload exists.
    """

    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    for item in _as_object_list(content):
        if isinstance(item, str) and item.strip():
            parts.append(item.strip())
        elif isinstance(item, dict):
            payload = cast(dict[str, object], item)
            text_obj = payload.get("text")
            if isinstance(text_obj, str) and text_obj.strip():
                parts.append(text_obj.strip())
    return " ".join(parts).strip()


def query_text_from_studio_input(state: object) -> str:
    """Read ``user_query`` or the last human Studio message.

    Args:
        state: Incoming Studio mapping. Extra keys are ignored.

    Returns:
        Stripped query text, or empty.
    """

    if not isinstance(state, dict):
        return ""
    mapping = cast(dict[str, object], state)
    raw = mapping.get("user_query")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    for item in reversed(_as_object_list(mapping.get("messages"))):
        if not isinstance(item, dict):
            continue
        typed = cast(dict[str, object], item)
        role = str(typed.get("role") or typed.get("type") or "").lower()
        if role not in {"human", "user"}:
            continue
        text = _text_from_message_content(typed.get("content"))
        if text:
            return text
    return ""


def _thread_id(config: RunnableConfig) -> str:
    """Return the Studio thread id, or ``studio-local``.

    Args:
        config: LangGraph runnable config.

    Returns:
        Non-empty thread identifier string.
    """

    configurable = config.get("configurable")
    if isinstance(configurable, dict):
        raw = configurable.get("thread_id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "studio-local"


def _payload_hash(query: str) -> str:
    """Return a 64-char SHA-256 hex digest that is not a production payload hash.

    Args:
        query: Studio query text.

    Returns:
        Hex digest.
    """

    return hashlib.sha256(f"{_STUDIO_PAYLOAD_PREFIX}{query}".encode()).hexdigest()


def studio_authorized_runtime(
    *,
    query: str,
    family: Phase6RouteFamily,
    thread_id: str,
) -> AuthorizedRuntimeContext:
    """Build a synthetic admit context from the server envelope table.

    Args:
        query: Studio query text used only for the local payload hash.
        family: Allow-listed Phase 6 family.
        thread_id: Studio thread id used for the synthetic conversation UUID.

    Returns:
        Frozen context with envelope ceilings. ``status`` is ``studio_local``.

    Raises:
        QueryCeilingError: If ``family`` is missing from the envelope table.
    """

    envelope = envelope_for_family(family)
    now = datetime.now(UTC)
    conversation_id = uuid5(STUDIO_NAMESPACE, f"conversation:{thread_id}")
    user_id = uuid5(STUDIO_NAMESPACE, "user:studio-local")
    return AuthorizedRuntimeContext(
        user_id=user_id,
        role=UserRole.MEMBER,
        authorization_version=1,
        conversation_id=conversation_id,
        run_id=uuid4(),
        reservation_id=uuid4(),
        reconnect=False,
        route_family=family,
        deadline_at=now + timedelta(seconds=envelope.deadline_seconds),
        recursion_limit=envelope.recursion_limit,
        correction_ceiling=envelope.correction_ceiling,
        subquestion_ceiling=envelope.subquestion_ceiling,
        model_call_ceiling=envelope.model_call_ceiling,
        tool_ceiling=envelope.tool_ceiling,
        discovery_ceiling=envelope.discovery_ceiling,
        manifest_ceiling=envelope.manifest_ceiling,
        side_effect_ceiling=envelope.side_effect_ceiling,
        reserved_amount_usd=envelope.envelope_usd,
        remaining_usd=envelope.envelope_usd,
        remaining_prompt_tokens=envelope.envelope_prompt_tokens,
        remaining_completion_tokens=envelope.envelope_completion_tokens,
        optimistic_version=1,
        heartbeat_at=now,
        payload_hash=_payload_hash(query),
        status="studio_local",
    )


def seed_studio_runtime(
    state: QueryGraphState,
    config: RunnableConfig,
) -> QueryGraphState:
    """Inject synthetic local context so Studio can run without FastAPI admit.

    State inputs:
        ``user_query`` and optional ``route_family`` / ``messages``.

    State outputs:
        Pending state with ``authorized_runtime``, or ``admission_rejected``
        when the family is not allow-listed.

    Persistence writes:
        None. This is not ``admit_query_run`` and writes no reservation.

    External/model calls:
        None.

    Budget/deadline behavior:
        Copies ``envelope_for_family`` ceilings. Does not enlarge them and
        does not debit company/user budget rows.

    Failure/fallback route:
        Unknown ``route_family`` sets ``admission_rejected`` and later routing
        ends. Empty queries are still admitted so ``prepare_query`` can reject
        them as ``empty_query``.

    Args:
        state: Incoming Studio mapping merged into query state.
        config: Runnable config; ``configurable.thread_id`` names the
            synthetic conversation.

    Returns:
        Pending query state with synthetic context, or a rejected pending
        state when the family is invalid.
    """

    query = query_text_from_studio_input(state)
    surface = state.get("routing_surface") or "production"
    requested: object = state.get("requested_manual_route")
    manual = requested if isinstance(requested, str) else None
    family_obj: object = state.get("route_family") or "hybrid"
    rejected = pending_query_state(
        user_query=query,
        routing_surface=surface,
        requested_manual_route=manual,
    )
    try:
        family = Phase6RouteFamily(str(family_obj))
        context = studio_authorized_runtime(
            query=query,
            family=family,
            thread_id=_thread_id(config),
        )
    except (ValueError, QueryCeilingError):
        return {
            **rejected,
            "status": "admission_rejected",
            "detail": "studio route_family is not an allow-listed Phase 6 family",
        }
    dumped = cast(dict[str, object], context.model_dump(mode="json"))
    return pending_query_state(
        dumped,
        user_query=query,
        routing_surface=surface,
        requested_manual_route=manual,
    )


graph: StudioCompiledGraph = build_query_graph(studio_local=True).compile()  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
"""Compiled Studio query graph. Checkpointer-free and unbound."""
