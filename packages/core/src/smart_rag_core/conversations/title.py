"""Bounded conversation-title sanitization and LLM skip rules."""

from __future__ import annotations

CONVERSATION_TITLE_MAX = 80
_FALLBACK_TITLES = frozenset({"", "chat", "untitled chat"})


def compact_conversation_title(text: str) -> str:
    """Collapse whitespace and bound a one-line session title.

    Args:
        text: Untrusted model or user text.

    Returns:
        Compact title, or ``Chat`` when empty after sanitizing.

    Side Effects:
        None.
    """

    compact = " ".join(text.replace("\r", " ").split())
    compact = compact.strip(" \t\"'`")
    compact = compact.strip("\u201c\u201d\u2018\u2019")
    if compact.endswith(".") and compact.count(".") == 1:
        compact = compact[:-1].rstrip()
    if compact == "":
        return "Chat"
    if len(compact) <= CONVERSATION_TITLE_MAX:
        return compact
    return f"{compact[: CONVERSATION_TITLE_MAX - 1].rstrip()}…"


def title_generation_excerpt(current_title: str | None, user_excerpt: str) -> str:
    """Choose the user text the title model should summarize.

    Args:
        current_title: Raw title from ``app.conversations``.
        user_excerpt: First persisted user message, or empty before persist.

    Returns:
        First user message when present; otherwise the stored title when it
        is not a generic Chat placeholder. Empty when neither is usable.

    Side Effects:
        None.
    """

    excerpt = user_excerpt.strip()
    if excerpt:
        return excerpt
    compact = compact_conversation_title(current_title or "")
    if compact.casefold() in _FALLBACK_TITLES:
        return ""
    return compact


def needs_llm_conversation_title(current_title: str | None, user_excerpt: str) -> bool:
    """Return whether the stored title is still a first-prompt fallback.

    Args:
        current_title: Raw title from ``app.conversations``.
        user_excerpt: First user message used to derive the create fallback.

    Returns:
        True when the title is missing, generic, or equals the compact
        first-prompt fallback. False when an LLM (or other) title is already
        stored.

    Side Effects:
        None.
    """

    fallback = compact_conversation_title(user_excerpt)
    current = compact_conversation_title(current_title or "")
    if current.casefold() in _FALLBACK_TITLES:
        return True
    return current == fallback


def conversation_title_json_schema() -> dict[str, object]:
    """Return the strict session-title structured-output schema.

    Returns:
        OpenAI ``json_schema`` document with ``title`` only.
    """

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title"],
        "properties": {
            "title": {
                "type": "string",
                "minLength": 1,
                "maxLength": CONVERSATION_TITLE_MAX,
            }
        },
    }


def mock_conversation_title_payload(user_excerpt: str) -> dict[str, object]:
    """Return a fixture title derived from the first user excerpt.

    Args:
        user_excerpt: First user message. Untrusted.

    Returns:
        ``{"title": ...}`` with a compact one-line description.

    Side Effects:
        None. No network or retrieval.
    """

    return {"title": compact_conversation_title(user_excerpt)}
