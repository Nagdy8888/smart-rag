"""Deterministic trigger, watermark, and bounded prompt policy for rolling memory."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from smart_rag_core.query_routing.models import MemoryRecord

MEMORY_CONTEXT_CHARS = 8000
SUMMARY_TRIGGER_CHARS = 6000
SUMMARY_TRIGGER_MESSAGES = 8
RECENT_MESSAGES = 4


@dataclass(frozen=True)
class CompactionPlan:
    """Only the acknowledged prefix is replaced; recent messages stay verbatim."""

    messages: str
    through_id: str
    through_created_at: str
    previous_summary: str


def chronological(records: Sequence[MemoryRecord]) -> list[MemoryRecord]:
    """RPC timestamps use UTC ISO format; IDs break equal-time ties."""
    return sorted(records, key=lambda r: (r.created_at, r.message_id))


def after_summary(
    records: Sequence[MemoryRecord], stored: Mapping[str, object]
) -> list[MemoryRecord]:
    """Do not replay messages already represented by the saved summary."""
    through = stored.get("through_message_id")
    created = stored.get("through_created_at")
    if not isinstance(through, str) or not isinstance(created, str):
        return chronological(records)
    return [
        r
        for r in chronological(records)
        if (r.created_at, r.message_id) > (created, through)
    ]


def compaction_plan(
    records: Sequence[MemoryRecord],
    stored: Mapping[str, object],
    *,
    max_message_bytes: int = 12_000,
) -> CompactionPlan | None:
    """Compact before the 12-message/8k prompt window rolls off, not after overflow."""
    pending = after_summary(records, stored)
    previous = stored.get("summary")
    previous = previous if isinstance(previous, str) else ""
    if (
        len(pending) < SUMMARY_TRIGGER_MESSAGES
        and sum(len(r.delimited) for r in pending) + len(previous)
        < SUMMARY_TRIGGER_CHARS
    ):
        return None
    older = pending[:-RECENT_MESSAGES]
    if not older:
        return None
    parts: list[str] = []
    last = older[0]
    for record in older:
        # Never send copied code/table/figure bodies to the memory store writer.
        body = re.sub(r"```[\s\S]*?```", "[code omitted]", record.content)
        body = re.sub(r"(?m)^\s*\|.*$", "[table omitted]", body)
        body = re.sub(r"\[\[figure:[^\]]+\]\]", "[figure]", body)
        if record.role == "assistant":
            body = body[:400]
        part = f"{record.role}: {body}"
        if len(("\n".join([*parts, part])).encode("utf8")) > max_message_bytes:
            break
        parts.append(part)
        last = record
    return (
        CompactionPlan("\n".join(parts), last.message_id, last.created_at, previous)
        if parts
        else None
    )


def bounded_memory(
    records: Sequence[MemoryRecord], stored: Mapping[str, object]
) -> list[MemoryRecord]:
    """Keep newest complete messages within the prompt budget, even on summary failure."""
    pending = after_summary(records, stored)
    summary = stored.get("summary")
    size = len(summary) if isinstance(summary, str) else 0
    kept: list[MemoryRecord] = []
    for record in reversed(pending):
        if size + len(record.delimited) > MEMORY_CONTEXT_CHARS:
            break
        kept.append(record)
        size += len(record.delimited)
    return list(reversed(kept))
