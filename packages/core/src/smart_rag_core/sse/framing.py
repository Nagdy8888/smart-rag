"""Manual SSE framing for FastAPI 0.141 StreamingResponse (no EventSourceResponse)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import cast

from smart_rag_core.sse.catalog import ALLOWED_SSE_EVENT_TYPES

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ParsedSseEvent:
    """One parsed SSE frame.

    Attributes:
        sequence: Event id, or None when omitted.
        event_type: Named event, or ``message`` when omitted.
        payload: JSON object payload, or empty mapping.
        ignored: True when the type is unknown and must not crash clients.
    """

    sequence: int | None
    event_type: str
    payload: dict[str, object]
    ignored: bool = False


def format_sse_event(
    *,
    sequence: int,
    event_type: str,
    payload: Mapping[str, object],
) -> str:
    """Render one SSE frame with id, event, and JSON data.

    Args:
        sequence: Monotonic run-local sequence written as ``id``.
        event_type: Allow-listed event name.
        payload: JSON object already sanitized.

    Returns:
        Wire text ending with a blank line.

    Raises:
        ValueError: When ``event_type`` is not allow-listed.
    """

    if event_type not in ALLOWED_SSE_EVENT_TYPES:
        raise ValueError("sse_event_type_unknown")
    data = json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=True)
    return f"id: {sequence}\nevent: {event_type}\ndata: {data}\n\n"


def parse_sse_frames(raw: str) -> Iterator[ParsedSseEvent]:
    """Parse concatenated SSE frames. Unknown types are logged and skipped.

    This is the tiny client helper: additive unknown events never crash.

    Args:
        raw: Complete or partial SSE body.

    Yields:
        Parsed frames. Unknown ``event`` names set ``ignored=True`` and are
        still yielded so callers can log; ``iter_known_sse_events`` drops them.
    """

    blocks = raw.split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        event_id: int | None = None
        event_type = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith(":"):
                continue
            if line.startswith("id:"):
                raw_id = line[3:].strip()
                if raw_id.isdigit():
                    event_id = int(raw_id)
                continue
            if line.startswith("event:"):
                event_type = line[6:].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        payload: dict[str, object] = {}
        if data_lines:
            joined = "\n".join(data_lines)
            decoded: object
            try:
                decoded = json.loads(joined)
            except json.JSONDecodeError:
                decoded = {"raw": joined}
            if isinstance(decoded, dict):
                payload = {
                    str(key): value
                    for key, value in cast(dict[object, object], decoded).items()
                }
        ignored = event_type not in ALLOWED_SSE_EVENT_TYPES
        if ignored:
            LOGGER.info(
                "Ignoring unknown SSE event type",
                extra={"event": "sse.unknown_event", "sse_event_type": event_type},
            )
        yield ParsedSseEvent(
            sequence=event_id,
            event_type=event_type,
            payload=payload,
            ignored=ignored,
        )


def iter_known_sse_events(raw: str) -> list[ParsedSseEvent]:
    """Return allow-listed events only. Unknown types are logged and dropped.

    Args:
        raw: SSE body.

    Returns:
        Parsed known events in order. Never raises for unknown types.
    """

    return [item for item in parse_sse_frames(raw) if not item.ignored]


def concat_sse(frames: Iterable[str]) -> str:
    """Join already-formatted frames.

    Args:
        frames: ``format_sse_event`` outputs.

    Returns:
        Concatenated wire body.
    """

    return "".join(frames)
