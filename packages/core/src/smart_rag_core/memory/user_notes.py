"""Bounded literal user statements survive omissions in model-written summaries."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from smart_rag_core.memory.compaction import after_summary
from smart_rag_core.query_routing.models import MemoryRecord

_COMMAND = re.compile(
    r"(?i)^(?:for this chat,?\s+)?(?:remember(?: that)?\s+"
    r"|update my(?:\s+[a-z]+){0,3}\s+preferences:\s*"
    r"|تذكر(?: أن| ان)?\s+|حدّث تفضيلاتي:\s*|حدث تفضيلاتي:\s*)(.+)$"
)
_SENSITIVE = re.compile(
    r"(?i)password|secret|credential|token|api.key|https?://|```|\[\[figure:|<<"
    r"|sk-[a-z0-9_-]{16,}|eyJ[a-z0-9_-]{16,}\."
)


def stored_user_notes(stored: Mapping[str, object]) -> tuple[str, ...]:
    """Keep the initial setup and two latest corrections, at most 600 characters."""
    value = stored.get("explicit_user_notes")
    if not isinstance(value, (list, tuple)):
        return ()
    notes: list[str] = []
    for item in cast(Sequence[object], value):
        if (
            isinstance(item, str)
            and 0 < len(item) <= 200
            and not _SENSITIVE.search(item)
            and item not in notes
        ):
            notes.append(item)
    return tuple(notes if len(notes) <= 3 else [notes[0], *notes[-2:]])


def merge_explicit_user_notes(
    stored: Mapping[str, object],
    records: Sequence[MemoryRecord],
    *,
    through_id: str,
    through_created_at: str,
) -> tuple[str, ...]:
    """Copy only actual user remember/update statements in the acknowledged prefix."""
    notes = list(stored_user_notes(stored))
    for record in after_summary(records, stored):
        if record.role != "user" or (record.created_at, record.message_id) > (
            through_created_at,
            through_id,
        ):
            continue
        for sentence in re.split(r"(?<=[.!?؟])\s+|\n", record.content):
            match = _COMMAND.fullmatch(sentence.strip())
            if match is None:
                continue
            statement = match.group(1).strip()
            if (
                not 0 < len(statement) <= 200
                or re.search(r"[?؟]$", statement)
                or _SENSITIVE.search(statement)
            ):
                continue
            if statement not in notes:
                notes.append(statement)
    return stored_user_notes({"explicit_user_notes": notes})
