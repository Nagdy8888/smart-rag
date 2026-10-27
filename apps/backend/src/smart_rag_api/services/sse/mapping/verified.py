"""Verified-answer extraction, hold/release, and catalog chunking.

Expected refusals and deadline/budget partials emit a non-empty token
plus one ``partial`` terminal. ``empty_answer`` is reserved for a
supposedly releasable verified payload that is blank.
"""

from __future__ import annotations

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.source_syntax import SOURCE_CODE_SYNTAX_INVALID
from smart_rag_core.security.untrusted import isolate_untrusted_text

from smart_rag_api.services.sse.mapping.citations import citation_preview
from smart_rag_api.services.sse.mapping.contracts import (
    CANONICAL_REFUSAL_TEXT,
    DEADLINE_EXHAUSTED_DETAIL,
    DEADLINE_REASONS,
    PARTIAL_STATUSES,
    TOKEN_DELTA_LIMIT,
)
from smart_rag_api.services.sse.mapping.usage import usage_event


def chunk_answer_text(text: str, *, limit: int = TOKEN_DELTA_LIMIT) -> tuple[str, ...]:
    """Split verified answer text into catalog-bounded ``token_delta`` chunks.

    Each piece is packed so ``isolate_untrusted_text`` of that piece stays
    within ``limit``. HTML escapes expand quotes and brackets, so a raw
    slice of 4096 characters can fail the catalog check. Joining the raw
    pieces equals the stripped answer.

    Args:
        text: Verified or refused prose. Never retrieved source.
        limit: Maximum escaped characters per chunk. Catalog max is 4096.

    Returns:
        Non-empty chunks, or an empty tuple when ``text`` is blank.
    """

    stripped = text.strip()
    if not stripped:
        return ()
    bounded = max(1, min(limit, TOKEN_DELTA_LIMIT))
    pieces: list[str] = []
    start = 0
    while start < len(stripped):
        low = start + 1
        high = len(stripped)
        best = start
        while low <= high:
            mid = (low + high) // 2
            if len(isolate_untrusted_text(stripped[start:mid])) <= bounded:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        if best <= start:
            best = start + 1
        pieces.append(stripped[start:best])
        start = best
    return tuple(pieces)


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


def _graceful_reason(
    update: dict[str, object], payload: AnswerPayload | None
) -> str | None:
    """Return a catalog partial reason for expected refusals and budgets.

    Args:
        update: Node return mapping.
        payload: Parsed answer, if any.

    Returns:
        Partial reason, or ``None`` when the update is a releasable
        verified completion.
    """

    raw_status = update.get("status")
    detail = update.get("detail")
    if detail == SOURCE_CODE_SYNTAX_INVALID:
        return SOURCE_CODE_SYNTAX_INVALID
    if isinstance(detail, str) and detail.startswith("verification_unavailable:"):
        return "verification_unavailable"
    if isinstance(detail, str) and detail in DEADLINE_REASONS:
        return DEADLINE_EXHAUSTED_DETAIL
    if isinstance(raw_status, str) and raw_status in DEADLINE_REASONS:
        return DEADLINE_EXHAUSTED_DETAIL
    if isinstance(raw_status, str) and raw_status in PARTIAL_STATUSES:
        return raw_status
    if payload is not None and payload.status in {"partial", "refused"}:
        return payload.status
    return None


def emit_verified_events(
    payload: AnswerPayload | None,
    update: dict[str, object],
) -> tuple[list[tuple[str, dict[str, object]]], bool, AnswerPayload | None]:
    """Build token deltas and one terminal for a verified payload.

    Expected refusals, insufficient evidence, and deadline/budget
    partials emit a limitation/partial sequence. ``empty_answer`` is
    reserved for a supposedly releasable verified payload that is blank.

    Args:
        payload: Final answer after verification, or None.
        update: Verify-node mapping for status/limitation.

    Returns:
        Events, whether a non-empty token delta was emitted, and the final
        payload when text was released.
    """

    graceful_reason = _graceful_reason(update, payload)
    text = payload.answer_text.strip() if payload is not None else ""
    if not text and graceful_reason is not None:
        text = CANONICAL_REFUSAL_TEXT
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
        origin: dict[str, object] = {"origin": payload.answer_origin.value}
        if payload.knowledge_result is not None:
            origin["knowledge_result"] = payload.knowledge_result.model_dump(
                mode="json"
            )
        events.append(("answer_origin", origin))
    for piece in chunks:
        events.append(("token_delta", {"delta": piece}))
    preview = citation_preview(payload) if payload is not None else None
    if preview is not None:
        events.append(preview)
    if usage is not None:
        events.append(usage)
    if graceful_reason is not None:
        if graceful_reason in {"verification_unavailable", SOURCE_CODE_SYNTAX_INVALID}:
            events.append(("limitation", {"code": graceful_reason}))
        if graceful_reason == DEADLINE_EXHAUSTED_DETAIL:
            events.append(("deadline", {}))
        if graceful_reason in {"insufficient_evidence", "refused"}:
            events.append(("limitation", {"code": "insufficient_evidence"}))
        events.append(("partial", {"reason": graceful_reason[:128]}))
        return events, True, payload
    events.append(("completed", {}))
    return events, True, payload
