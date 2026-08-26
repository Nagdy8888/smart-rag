"""Verified-answer extraction, hold/release, and catalog chunking."""

from __future__ import annotations

from smart_rag_core.query_answer.models import AnswerPayload

from smart_rag_api.services.sse.mapping.citations import citation_preview
from smart_rag_api.services.sse.mapping.contracts import (
    PARTIAL_STATUSES,
    TOKEN_DELTA_LIMIT,
)
from smart_rag_api.services.sse.mapping.usage import usage_event


def chunk_answer_text(text: str, *, limit: int = TOKEN_DELTA_LIMIT) -> tuple[str, ...]:
    """Split verified answer text into catalog-bounded ``token_delta`` chunks.

    Args:
        text: Verified or refused prose. Never retrieved source.
        limit: Maximum characters per chunk. Catalog max is 4096.

    Returns:
        Non-empty chunks, or an empty tuple when ``text`` is blank.
    """

    stripped = text.strip()
    if not stripped:
        return ()
    bounded = max(1, min(limit, TOKEN_DELTA_LIMIT))
    return tuple(
        stripped[offset : offset + bounded]
        for offset in range(0, len(stripped), bounded)
    )


def payload_from_update(update: dict[str, object]) -> AnswerPayload | None:
    """Parse ``AnswerPayload`` from a node update when present.

    Args:
        update: Node return mapping.

    Returns:
        Validated payload or None when ``answer`` is missing/invalid.
    """

    raw = update.get("answer")
    if not isinstance(raw, dict):
        return None
    try:
        return AnswerPayload.model_validate(raw)
    except (TypeError, ValueError):
        return None


def emit_verified_events(
    payload: AnswerPayload | None,
    update: dict[str, object],
) -> tuple[list[tuple[str, dict[str, object]]], bool, AnswerPayload | None]:
    """Build token deltas and one terminal for a verified payload.

    Args:
        payload: Final answer after verification, or None.
        update: Verify-node mapping for status/limitation.

    Returns:
        Events, whether a non-empty token delta was emitted, and the final
        payload when text was released.
    """

    text = payload.answer_text.strip() if payload is not None else ""
    chunks = chunk_answer_text(text)
    usage = usage_event(update)
    if not chunks:
        empty: list[tuple[str, dict[str, object]]] = []
        if usage is not None:
            empty.append(usage)
        empty.append(("error", {"code": "empty_answer"}))
        return empty, False, None
    events: list[tuple[str, dict[str, object]]] = []
    if payload is not None and payload.answer_origin is not None:
        events.append(("answer_origin", {"origin": payload.answer_origin.value}))
    for piece in chunks:
        events.append(("token_delta", {"delta": piece}))
    preview = citation_preview(payload) if payload is not None else None
    if preview is not None:
        events.append(preview)
    if usage is not None:
        events.append(usage)
    raw_status = update.get("status")
    answer_status = payload.status if payload is not None else "complete"
    if (
        isinstance(raw_status, str) and raw_status in PARTIAL_STATUSES
    ) or answer_status in {"partial", "refused"}:
        reason = (
            raw_status
            if isinstance(raw_status, str) and raw_status
            else answer_status
        )
        if raw_status == "verified_partial" or answer_status == "partial":
            events.append(("deadline", {"route_family": None}))
        events.append(("partial", {"reason": str(reason)[:128]}))
        return events, True, payload
    events.append(("completed", {}))
    return events, True, payload
