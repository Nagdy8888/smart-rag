"""Hold draft answers until verification, then emit catalog SSE drafts."""

from __future__ import annotations

from smart_rag_core.query_answer.models import AnswerPayload

from smart_rag_api.services.sse.mapping.contracts import (
    DRAFT_ANSWER_NODES,
    REJECT_STATUSES,
    VERIFY_ANSWER_NODE,
)
from smart_rag_api.services.sse.mapping.limitations import limitation_from_update
from smart_rag_api.services.sse.mapping.status import status_event
from smart_rag_api.services.sse.mapping.verified import (
    emit_verified_events,
    payload_from_update,
)


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
            events.append(status_event(node_name, update))
            limitation = limitation_from_update(update)
            if limitation is not None:
                events.append(limitation)
            parsed = payload_from_update(update)
            if node_name in DRAFT_ANSWER_NODES:
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
                and raw_status in REJECT_STATUSES
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

        events, emitted_delta, final = emit_verified_events(payload, update)
        self.terminal_emitted = True
        if emitted_delta:
            self.emitted_token_delta = True
            self._final = final
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
