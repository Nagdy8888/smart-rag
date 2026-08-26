"""Strict custom progress decoding with defensive start deduplication."""

from __future__ import annotations

from typing import Final, cast

from smart_rag_core.sse.catalog import SseProgressPhase

from smart_rag_api.services.sse.mapping.diagnostics import log_dropped_custom

_NODE_START_KEYS: Final[frozenset[str]] = frozenset({"kind", "stage"})
_TOOL_PROGRESS_KEYS: Final[frozenset[str]] = frozenset({"kind", "tool_key", "phase"})
_LEGAL_PHASES: Final[frozenset[str]] = frozenset({"started", "completed", "failed"})


class CustomProgressDecoder:
    """Decode custom writer payloads into catalog SSE drafts.

    Attributes:
        open_starts: Stages that emitted ``started`` and have not completed.
    """

    def __init__(self) -> None:
        """Create a decoder with no open starts."""

        self.open_starts: set[str] = set()

    def consume_custom(
        self, data: object
    ) -> list[tuple[str, dict[str, object]]]:
        """Translate one custom mapping into zero or one catalog draft.

        Extra keys, unknown kinds, and malformed values are dropped. Payload
        values are never logged.

        Args:
            data: Custom writer payload.

        Returns:
            Catalog drafts, or an empty list when the payload is dropped.
        """

        if not isinstance(data, dict):
            log_dropped_custom(reason="not_mapping", kind=None, extra_keys=())
            return []
        typed = {
            str(key): value
            for key, value in cast(dict[object, object], data).items()
        }
        kind = typed.get("kind")
        kind_label = kind if isinstance(kind, str) else None
        if kind == "node_start":
            return self._node_start(typed, kind_label)
        if kind == "tool_progress":
            return self._tool_progress(typed, kind_label)
        log_dropped_custom(
            reason="unknown_kind",
            kind=kind_label,
            extra_keys=tuple(sorted(typed)[:16]),
        )
        return []

    def note_stage_terminal(self, stage: str) -> None:
        """Clear a defensive open-start after the matching updates part.

        Args:
            stage: Production node name.
        """

        self.open_starts.discard(stage)

    def _node_start(
        self, typed: dict[str, object], kind_label: str | None
    ) -> list[tuple[str, dict[str, object]]]:
        """Map ``node_start`` to a running status with ``phase=started``.

        Args:
            typed: String-keyed custom mapping.
            kind_label: String kind, if present.

        Returns:
            One status draft, or empty when malformed or duplicate.
        """

        extra = tuple(sorted(set(typed) - _NODE_START_KEYS))
        stage = typed.get("stage")
        if extra or not isinstance(stage, str) or not stage:
            log_dropped_custom(
                reason="malformed_node_start",
                kind=kind_label,
                extra_keys=extra,
            )
            return []
        bounded = stage[:64]
        if bounded in self.open_starts:
            log_dropped_custom(
                reason="duplicate_open_start",
                kind=kind_label,
                extra_keys=(),
            )
            return []
        self.open_starts.add(bounded)
        return [
            (
                "status",
                {"stage": bounded, "status": "running", "phase": "started"},
            )
        ]

    def _tool_progress(
        self, typed: dict[str, object], kind_label: str | None
    ) -> list[tuple[str, dict[str, object]]]:
        """Map ``tool_progress`` to the public catalog event.

        Args:
            typed: String-keyed custom mapping.
            kind_label: String kind, if present.

        Returns:
            One ``tool_progress`` draft, or empty when malformed.
        """

        extra = tuple(sorted(set(typed) - _TOOL_PROGRESS_KEYS))
        tool_key = typed.get("tool_key")
        phase = typed.get("phase")
        if (
            extra
            or not isinstance(tool_key, str)
            or not tool_key
            or phase not in _LEGAL_PHASES
        ):
            log_dropped_custom(
                reason="malformed_tool_progress",
                kind=kind_label,
                extra_keys=extra,
            )
            return []
        typed_phase: SseProgressPhase = cast(SseProgressPhase, phase)
        return [
            (
                "tool_progress",
                {"tool_key": tool_key[:64], "phase": typed_phase},
            )
        ]
