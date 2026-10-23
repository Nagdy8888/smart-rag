"""Bounded user preferences survive rolling topic summaries without becoming evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.memory.compaction import after_summary
from smart_rag_core.memory.user_notes import stored_user_notes
from smart_rag_core.query_routing.models import MemoryRecord

_DURABLE_LANGUAGE = re.compile(
    r"(?i)\b(?:prefer|default|always)\b|from now|for this chat"
    r"|language preference\s*(?:is|:)"
    r"|تفضيل|أفضل|افضل|دائم|من الآن|من الان|طوال|لهذه المحادثة"
)
_LOCAL_LANGUAGE = re.compile(
    r"(?i)this (?:answer|question|response)|هذه الإجابة|هذا السؤال"
)
_EXPLICIT_POLICY_START = re.compile(
    r"(?i)^(?:please\s+)?(?:prefer\b|I prefer\b|my\b|from now\b|for this chat\b"
    r"|always (?:answer|reply|respond)\b|default\b"
    r"|أفضل|افضل|تفضيلي|من الآن|من الان|لهذه المحادثة|أجب دائم|اجب دائم|اللغة المفضلة)"
)


def _language_contexts(quote: str, messages: Sequence[str]) -> list[str]:
    """Resolve an abbreviated quote to its actual user sentence, never assistant prose."""
    contexts: list[str] = []
    for message in messages:
        if quote not in message:
            continue
        sentences = re.split(r"(?<=[.!?؟])\s+|\n", message)
        contexts.extend(sentence for sentence in sentences if quote in sentence)
    return contexts


class PreferenceUpdate(BaseModel):
    """A proposed preference must quote an actual user message in the compacted prefix."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    value: str = Field(min_length=1, max_length=100)
    user_quote: str = Field(min_length=1, max_length=180)


def stored_preferences(stored: Mapping[str, object]) -> dict[str, str]:
    """Copy at most eight short scalars, with a combined 600-character ceiling."""
    raw = stored.get("preferences")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in cast(dict[object, object], raw).items():
        if (
            isinstance(key, str)
            and isinstance(value, str)
            and re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key)
            and 0 < len(value) <= 100
            and not re.search(r"password|secret|credential|token|api_key", key)
            and not re.search(r"sk-[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]{16,}\.", value)
        ):
            candidate = {**result, key: value}
            if (
                len(candidate) <= 8
                and sum(len(k) + len(v) for k, v in candidate.items()) <= 600
            ):
                result = candidate
    return result


def merge_preference_updates(
    stored: Mapping[str, object],
    updates: Sequence[PreferenceUpdate],
    records: Sequence[MemoryRecord],
    *,
    through_id: str,
    through_created_at: str,
) -> dict[str, str]:
    """Accept only literal user-backed updates; omitted keys retain their old values."""
    result = stored_preferences(stored)
    user_messages = [
        record.content
        for record in after_summary(records, stored)
        if record.role == "user"
        and (record.created_at, record.message_id) <= (through_created_at, through_id)
    ]
    language_updated = False
    for update in updates:
        if update.value not in update.user_quote or not any(
            update.user_quote in text for text in user_messages
        ):
            continue
        if re.search(r"language|locale", update.key):
            # A literal quote proves authorship, not that a one-turn format
            # request changes the user's durable default.
            contexts = _language_contexts(update.user_quote, user_messages)
            if not any(
                _DURABLE_LANGUAGE.search(text) and not _LOCAL_LANGUAGE.search(text)
                for text in contexts
            ):
                continue
            language_updated = True
        result = stored_preferences(
            {"preferences": {**result, update.key: update.value}}
        )
    if not language_updated:
        # Preserve a literal explicit policy if the model omitted it. This is
        # user context only, bounded and subject to the same store sanitizer.
        key = next(
            (k for k in result if re.search(r"language|locale", k)),
            "language_preference",
        )
        for message in reversed(user_messages):
            for sentence in reversed(re.split(r"(?<=[.!?؟])\s+|\n", message)):
                sentence = sentence.strip()
                if (
                    0 < len(sentence) <= 100
                    and _EXPLICIT_POLICY_START.search(sentence)
                    and not re.search(r"[?؟]$", sentence)
                    and _DURABLE_LANGUAGE.search(sentence)
                    and not _LOCAL_LANGUAGE.search(sentence)
                    and re.search(
                        r"(?i)\b(?:English|Arabic|language)\b|الإنجليزية|الانجليزية|العربية|اللغة",
                        sentence,
                    )
                    and not re.search(
                        r"(?i)password|secret|credential|token|api.key|https?://",
                        sentence,
                    )
                ):
                    return stored_preferences(
                        {"preferences": {**result, key: sentence}}
                    )
    return result


def summary_with_preferences(stored: Mapping[str, object]) -> str:
    """Put stable user details first and fit topic prose into the remaining memory slot."""
    preferences = stored_preferences(stored)
    heading = "User-provided preferences (untrusted):\n" if preferences else ""
    prefix = heading + "\n".join(
        f"{key}: {value}" for key, value in preferences.items()
    )
    notes = stored_user_notes(stored)
    if notes:
        prefix += (
            "\n" if prefix else ""
        ) + "Explicit user statements, oldest to newest (untrusted):\n"
        prefix += "\n".join(f"- {note}" for note in notes)
    summary = stored.get("summary")
    summary = summary if isinstance(summary, str) else ""
    return (prefix + ("\nTopics: " if prefix else "") + summary)[:1400]
