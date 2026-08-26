"""Studio input schemas and query-text extraction."""

from __future__ import annotations

from typing import Annotated, TypeAlias, cast
from uuid import UUID

from langchain_core.messages import AnyMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict

from smart_rag_agents.query.state import QueryGraphState

STUDIO_NAMESPACE = UUID("8f1c0d2a-4b7e-4c9a-9d31-7a6e5f4b3c21")
"""Stable UUID namespace for Studio conversation/user ids. Not an auth subject."""


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
    messages: Annotated[list[AnyMessage], add_messages]


class StudioQueryState(QueryGraphState):
    """Query state extended with LangGraph's standard chat message channel.

    Attributes:
        messages: Human and assistant turns merged by ``add_messages``. The
            channel is local to the Studio export and is not production
            conversation memory or an authorization source.
    """

    messages: Annotated[list[AnyMessage], add_messages]


StudioCompiledGraph: TypeAlias = CompiledStateGraph[
    StudioQueryState,
    None,
    StudioQueryInput,
    StudioQueryState,
]


def as_object_list(value: object) -> list[object]:
    """Return ``value`` as a list of objects, or empty when it is not a list.

    Args:
        value: Untrusted Studio payload fragment.

    Returns:
        A shallow copy typed as ``list[object]``.
    """

    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def text_from_message_content(content: object) -> str:
    """Return plain text from a Studio/LangChain message content field.

    Args:
        content: String or list of text-part mappings.

    Returns:
        Stripped text, or empty when no string payload exists.
    """

    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    for item in as_object_list(content):
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
    for item in reversed(as_object_list(mapping.get("messages"))):
        if isinstance(item, BaseMessage):
            role = item.type.lower()
            content = item.content
        elif isinstance(item, dict):
            typed = cast(dict[str, object], item)
            role = str(typed.get("role") or typed.get("type") or "").lower()
            content = typed.get("content")
        else:
            continue
        if role not in {"human", "user"}:
            continue
        text = text_from_message_content(content)
        if text:
            return text
    return ""


def studio_thread_id(config: RunnableConfig, *, default: str) -> str:
    """Return the Studio thread id, or ``default``.

    Args:
        config: LangGraph runnable config.
        default: Fallback identifier when ``thread_id`` is absent.

    Returns:
        Non-empty thread identifier string.
    """

    configurable = config.get("configurable")
    if isinstance(configurable, dict):
        raw = configurable.get("thread_id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return default
