"""Deterministic local Studio seed, emit, and unbound graph."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4, uuid5

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from smart_rag_core.query_admission.ceilings import envelope_for_family
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_admission.exceptions import QueryCeilingError
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import UserRole

from smart_rag_agents.query.graph import build_query_graph
from smart_rag_agents.query.state import QueryGraphState, pending_query_state
from smart_rag_agents.query.studio.input import (
    STUDIO_NAMESPACE,
    StudioCompiledGraph,
    StudioQueryState,
    query_text_from_studio_input,
    studio_thread_id,
)
from smart_rag_agents.query.studio.tracing import apply_studio_langsmith_flags

_STUDIO_PAYLOAD_PREFIX = "langgraph-studio-local:"


def studio_usage_label(state: QueryGraphState) -> str:
    """Return a short token-consumption line when the run used a model.

    Args:
        state: Terminal query state with optional accumulated tokens.

    Returns:
        ``N prompt · M completion``, or empty when both counts are zero.
    """

    prompt = state.get("prompt_tokens")
    completion = state.get("completion_tokens")
    if not isinstance(prompt, int) or isinstance(prompt, bool):
        return ""
    if not isinstance(completion, int) or isinstance(completion, bool):
        return ""
    if prompt <= 0 and completion <= 0:
        return ""
    return f"{prompt:,} prompt · {completion:,} completion"


def with_studio_usage(text: str, state: QueryGraphState) -> str:
    """Append token consumption under Studio answer text.

    Args:
        text: Safe answer or status fallback.
        state: Terminal query state.

    Returns:
        ``text`` unchanged when the run spent no tokens.
    """

    usage = studio_usage_label(state)
    if not usage:
        return text
    return f"{text}\n\n{usage}"


def answer_text(value: object) -> str:
    """Return non-empty ``answer_text`` from an answer-shaped mapping.

    Args:
        value: Untrusted graph-state fragment.

    Returns:
        Stripped answer text, or an empty string.
    """

    if not isinstance(value, dict):
        return ""
    mapping = cast(dict[str, object], value)
    text = mapping.get("answer_text")
    return text.strip() if isinstance(text, str) else ""


def studio_response_text(state: QueryGraphState) -> str:
    """Choose the safe terminal text rendered as the Studio assistant turn.

    Args:
        state: Terminal query state.

    Returns:
        Verified answer text when present, then draft answer text, then a safe
        status/detail fallback. Provider token totals are appended only when
        the run spent tokens. The function never fabricates retrieval
        evidence.
    """

    verification = state.get("verification")
    if isinstance(verification, dict):
        text = answer_text(verification.get("answer"))
        if text:
            return with_studio_usage(text, state)
    text = answer_text(state.get("answer"))
    if text:
        return with_studio_usage(text, state)
    status = str(state.get("status") or "finished").replace("_", " ")
    detail = str(state.get("detail") or "").strip()
    fallback = (
        f"{status}: {detail}" if detail else f"Studio run {status} without an answer."
    )
    return with_studio_usage(fallback, state)


def emit_studio_response(
    state: StudioQueryState,
) -> dict[str, list[AnyMessage]]:
    """Append one assistant message for LangSmith Studio Chat mode.

    State inputs:
        Terminal ``answer`` / ``verification`` and safe status diagnostics.

    State outputs:
        One ``AIMessage`` update on the Studio-only ``messages`` channel.

    Persistence writes:
        None. The local Agent Server may retain the thread in its development
        store; this node does not write application conversation memory.

    External/model calls:
        None.

    Budget/deadline behavior:
        Consumes no reservation, token, model, tool, or retry budget.

    Failure/fallback route:
        Missing answer text emits the existing safe status/detail rather than
        claiming successful retrieval.

    Args:
        state: Terminal query graph state.

    Returns:
        A partial state update containing one assistant message.
    """

    return {"messages": [AIMessage(content=studio_response_text(state))]}


def payload_hash(query: str) -> str:
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
        payload_hash=payload_hash(query),
        status="studio_local",
    )


def seed_studio_runtime(
    state: StudioQueryState,
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
            thread_id=studio_thread_id(config, default="studio-local"),
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


apply_studio_langsmith_flags()

graph: StudioCompiledGraph = build_query_graph(studio_local=True).compile()  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
"""Compiled Studio query graph. Checkpointer-free and unbound."""
