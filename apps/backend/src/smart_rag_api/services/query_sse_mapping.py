"""Translate LangGraph ``updates`` envelopes into allow-listed SSE drafts.

Verified-final delivery: draft ``answer_text`` from ``generate_answer`` is held
until ``verify_answer`` completes. Compatibility ``token_delta`` chunks then
carry the verified/refused/partial prose. Empty successful completion is
impossible.
"""

from __future__ import annotations

from typing import Final

from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_routing.constants import LIMITATION_VERIFIER_OMITTED_LINKS
from smart_rag_core.sse.catalog import ALLOWED_SSE_EVENT_TYPES

GENERATE_ANSWER_NODE: Final[str] = "generate_answer"
VERIFY_ANSWER_NODE: Final[str] = "verify_answer"
TOKEN_DELTA_LIMIT: Final[int] = 4096
ALLOWED_SSE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "stage",
        "status",
        "code",
        "reason",
        "route_family",
        "from_route",
        "to_route",
        "delta",
        "citation_ids",
        "ranks",
        "prompt_tokens",
        "completion_tokens",
        "tool_keys",
        "sse_schema_version",
    }
)
_PARTIAL_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "verified_partial",
        "insufficient_evidence",
        "refused",
    }
)
_REJECT_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "admission_rejected",
        "routing_rejected",
    }
)


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


def _status_event(
    node_name: str, update: dict[str, object]
) -> tuple[str, dict[str, object]]:
    """Build one allow-listed status event for a node update.

    Args:
        node_name: Compiled graph node name.
        update: Node return mapping.

    Returns:
        ``status`` event with stage and status only.
    """

    raw_status = update.get("status")
    status = (
        raw_status[:64]
        if isinstance(raw_status, str) and raw_status
        else "running"
    )
    return ("status", {"stage": node_name[:64], "status": status})


def _citation_preview(
    payload: AnswerPayload,
) -> tuple[str, dict[str, object]] | None:
    """Build citation preview IDs without passage text.

    Args:
        payload: Verified answer payload.

    Returns:
        ``citation_preview`` event or None when no identifiers exist.
    """

    identifiers: list[str] = []
    for citation in (*payload.citations, *payload.table_citations):
        if citation.chunk_id:
            identifiers.append(citation.chunk_id)
        elif citation.table_id:
            identifiers.append(citation.table_id)
    if not identifiers:
        return None
    ranks = tuple(range(1, len(identifiers) + 1))
    return (
        "citation_preview",
        {"citation_ids": tuple(identifiers), "ranks": ranks},
    )


def _limitation_from_update(
    update: dict[str, object],
) -> tuple[str, dict[str, object]] | None:
    """Return a signed limitation when the verifier omitted links.

    Args:
        update: Node return mapping.

    Returns:
        ``limitation`` event or None.
    """

    verification = update.get("verification")
    if not isinstance(verification, dict):
        return None
    omitted = verification.get("omitted_link_ids")
    if omitted:
        return ("limitation", {"code": LIMITATION_VERIFIER_OMITTED_LINKS})
    return None


def _payload_from_update(update: dict[str, object]) -> AnswerPayload | None:
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


class QuerySseMapper:
    """Hold draft answers until verification, then emit catalog SSE drafts.

    Attributes:
        verified: True after ``verify_answer`` has been consumed.
        emitted_token_delta: True after at least one non-empty token delta.
        terminal_emitted: True after a terminal draft was produced.
    """

    def __init__(self) -> None:
        """Create an empty mapper."""

        self._draft: AnswerPayload | None = None
        self._final: AnswerPayload | None = None
        self.verified = False
        self.emitted_token_delta = False
        self.terminal_emitted = False

    def consume_chunk(self, chunk: object) -> list[tuple[str, dict[str, object]]]:
        """Translate one compiled ``updates`` chunk into SSE drafts.

        Args:
            chunk: Node-keyed mapping ``{node_name: update}``. Other shapes
                are ignored.

        Returns:
            Allow-listed ``(event_type, payload)`` drafts. Never includes
            unverified ``answer_text``.
        """

        if self.terminal_emitted:
            return []
        if not isinstance(chunk, dict):
            return []
        events: list[tuple[str, dict[str, object]]] = []
        for raw_name, raw_update in chunk.items():
            node_name = str(raw_name)
            update: dict[str, object] = {}
            if isinstance(raw_update, dict):
                update = {
                    str(key): value
                    for key, value in raw_update.items()
                    if str(key) not in {"passage", "snippet", "html", "traceback"}
                }
            events.append(_status_event(node_name, update))
            limitation = _limitation_from_update(update)
            if limitation is not None:
                events.append(limitation)
            parsed = _payload_from_update(update)
            if node_name == GENERATE_ANSWER_NODE:
                if parsed is not None:
                    self._draft = parsed
                continue
            if node_name == VERIFY_ANSWER_NODE:
                self.verified = True
                final = parsed or self._draft
                events.extend(self._emit_verified(final, update))
                continue
            raw_status = update.get("status")
            if (
                isinstance(raw_status, str)
                and raw_status in _REJECT_STATUSES
                and not self.verified
            ):
                events.append(("error", {"code": raw_status}))
                self.terminal_emitted = True
                return events
        return events

    def finish(self) -> list[tuple[str, dict[str, object]]]:
        """Close the stream with exactly one terminal when none was emitted.

        Returns:
            Terminal drafts. ``completed`` is used only after a non-empty
            ``token_delta``. Otherwise ``error``.
        """

        if self.terminal_emitted:
            return []
        if self.emitted_token_delta:
            self.terminal_emitted = True
            return [("completed", {})]
        self.terminal_emitted = True
        if self._draft is not None and not self.verified:
            return [("error", {"code": "unverified_answer"})]
        return [("error", {"code": "empty_answer"})]

    def _emit_verified(
        self,
        payload: AnswerPayload | None,
        update: dict[str, object],
    ) -> list[tuple[str, dict[str, object]]]:
        """Emit token deltas and one terminal for a verified payload.

        Args:
            payload: Final answer after verification, or None.
            update: Verify-node mapping for status/limitation.

        Returns:
            SSE drafts including exactly one terminal.
        """

        text = payload.answer_text.strip() if payload is not None else ""
        chunks = chunk_answer_text(text)
        if not chunks:
            self.terminal_emitted = True
            return [("error", {"code": "empty_answer"})]
        self._final = payload
        events: list[tuple[str, dict[str, object]]] = []
        for piece in chunks:
            events.append(("token_delta", {"delta": piece}))
            self.emitted_token_delta = True
        preview = _citation_preview(payload) if payload is not None else None
        if preview is not None:
            events.append(preview)
        raw_status = update.get("status")
        answer_status = payload.status if payload is not None else "complete"
        if (
            isinstance(raw_status, str) and raw_status in _PARTIAL_STATUSES
        ) or answer_status in {"partial", "refused"}:
            reason = (
                raw_status
                if isinstance(raw_status, str) and raw_status
                else answer_status
            )
            if raw_status == "verified_partial" or answer_status == "partial":
                events.append(("deadline", {"route_family": None}))
            events.append(("partial", {"reason": str(reason)[:128]}))
            self.terminal_emitted = True
            return events
        events.append(("completed", {}))
        self.terminal_emitted = True
        return events

    @property
    def verified_text(self) -> str:
        """Return verified answer prose after a successful mapping.

        Returns:
            Final answer text, or empty when verification did not emit text.
        """

        if self._final is None:
            return ""
        return self._final.answer_text.strip()


def assert_catalog_event(event_type: str, payload: dict[str, object]) -> None:
    """Fail closed when a mapper draft leaves the SSE catalog.

    Args:
        event_type: Draft event name.
        payload: Draft payload.

    Raises:
        ValueError: Unknown type or disallowed payload key.
    """

    if event_type not in ALLOWED_SSE_EVENT_TYPES:
        raise ValueError("sse_event_not_allowlisted")
    extra = set(payload) - ALLOWED_SSE_FIELDS
    if extra:
        raise ValueError("sse_payload_field_not_allowlisted")
