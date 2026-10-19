"""Hold draft answers until verification, then emit catalog SSE drafts."""

from __future__ import annotations

from typing import Final, cast

from smart_rag_core.query_answer.models import AnswerPayload

from smart_rag_api.services.sse.mapping.contracts import (
    DRAFT_ANSWER_NODES,
    ORGANIZE_ANSWER_NODE,
    PARTIAL_STATUSES,
    VERIFY_ANSWER_NODE,
)
from smart_rag_api.services.sse.mapping.limitations import limitations_from_update
from smart_rag_api.services.sse.mapping.progress import CustomProgressDecoder
from smart_rag_api.services.sse.mapping.status import (
    reject_terminal_events,
    status_event,
)
from smart_rag_api.services.sse.mapping.verified import (
    emit_verified_events,
    payload_from_update,
)


def _release_gate_status(status: str) -> list[tuple[str, dict[str, object]]]:
    """Return verify-answer started then completed for skipped verifiers.

    Generate-time expected refusals skip the verifier node. Ask still
    requires ``verify_answer`` completed before ``token_delta``. Route
    progress also requires a matching started event so skipped nodes
    stay visible as one started/completed pair.

    Args:
        status: Expected graceful node status copied onto the completed
            event.

    Returns:
        Catalog ``status`` events for ``verify_answer``.
    """

    return [
        (
            "status",
            {
                "stage": VERIFY_ANSWER_NODE,
                "status": "running",
                "phase": "started",
            },
        ),
        (
            "status",
            {
                "stage": VERIFY_ANSWER_NODE,
                "status": status[:64],
                "phase": "completed",
            },
        ),
    ]


_STRIP_UPDATE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "passage",
        "snippet",
        "html",
        "traceback",
        "excerpt",
        "excerpts",
        "web_sources",
        "body",
        "text",
    }
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
        self._pending_payload: AnswerPayload | None = None
        self._pending_update: dict[str, object] = {}
        self.verified = False
        self.emitted_token_delta = False
        self.terminal_emitted = False
        self._progress = CustomProgressDecoder()

    def consume_custom(self, data: object) -> list[tuple[str, dict[str, object]]]:
        """Translate one custom writer payload into catalog drafts.

        Args:
            data: Custom ``get_stream_writer`` mapping.

        Returns:
            Allow-listed drafts. Malformed payloads yield nothing.
        """

        if self.terminal_emitted:
            return []
        return self._progress.consume_custom(data)

    def consume_chunk(self, chunk: object) -> list[tuple[str, dict[str, object]]]:
        """Translate one compiled ``updates`` chunk into SSE drafts.

        Expected ``insufficient_evidence`` / ``refused`` / ``verified_partial``
        outcomes become one ``partial`` terminal even when later nodes,
        including ``verify_answer``, are skipped. A synthetic
        ``verify_answer`` status is emitted first so Ask can accept the
        refusal tokens.

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
        typed_chunk = cast(dict[object, object], chunk)
        for raw_name, raw_update in typed_chunk.items():
            node_name = str(raw_name)
            update: dict[str, object] = {}
            if isinstance(raw_update, dict):
                typed_update = cast(dict[object, object], raw_update)
                update = {
                    str(key): value
                    for key, value in typed_update.items()
                    if str(key) not in _STRIP_UPDATE_KEYS
                }
            events.append(status_event(node_name, update))
            self._progress.note_stage_terminal(node_name[:64])
            events.extend(limitations_from_update(update))
            parsed = payload_from_update(update)
            if node_name in DRAFT_ANSWER_NODES and parsed is not None:
                self._draft = parsed
            if node_name == VERIFY_ANSWER_NODE:
                self.verified = True
                self._pending_payload = parsed or self._draft
                self._pending_update = update
                continue
            if node_name == ORGANIZE_ANSWER_NODE:
                self.verified = True
                events.extend(
                    self._emit_verified(
                        parsed or self._pending_payload or self._draft,
                        update,
                    )
                )
                continue
            if not self.verified:
                raw_status = update.get("status")
                if isinstance(raw_status, str) and raw_status in PARTIAL_STATUSES:
                    events.extend(_release_gate_status(raw_status))
                    events.extend(self._emit_verified(parsed or self._draft, update))
                    return events
                reject_events = reject_terminal_events(update)
                if reject_events:
                    events.extend(reject_events)
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
        if self._pending_payload is not None and not self.emitted_token_delta:
            return self._emit_verified(self._pending_payload, self._pending_update)
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
        """Emit token deltas and one terminal for a released payload.

        Also used for generate-time expected refusals when the verifier
        node is skipped.

        Args:
            payload: Final answer after verification, or a refusal payload.
            update: Node mapping for status/limitation.

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
