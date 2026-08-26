"""LangGraph adapter for core optional-tool progress events."""

from __future__ import annotations

from typing import Literal

from langgraph.config import get_stream_writer
from smart_rag_core.tools.progress import ToolProgressPhase
from typing_extensions import TypedDict


class ToolProgressCustom(TypedDict):
    """Safe custom payload for one optional-tool phase.

    Attributes:
        kind: Constant ``tool_progress`` discriminator.
        tool_key: Selected catalog key.
        phase: ``started``, ``completed``, or ``failed``.
    """

    kind: Literal["tool_progress"]
    tool_key: str
    phase: ToolProgressPhase


class LangGraphToolProgressReporter:
    """Write custom tool-progress events for selected keys only.

    Keys that were not reported by ``selected`` are dropped. The writer
    payload contains only ``kind``, ``tool_key``, and ``phase``.
    """

    def __init__(self) -> None:
        """Create a reporter with an empty selected-key set."""

        self._selected: tuple[str, ...] = ()

    def selected(self, tool_keys: tuple[str, ...]) -> None:
        """Store the authorized selected keys for later phase checks.

        Args:
            tool_keys: Role-visible catalog keys.
        """

        self._selected = tool_keys

    def phase(self, tool_key: str, phase: ToolProgressPhase) -> None:
        """Emit one custom event when ``tool_key`` was selected.

        Args:
            tool_key: Catalog key.
            phase: Execution phase.
        """

        if tool_key not in self._selected:
            return
        payload: ToolProgressCustom = {
            "kind": "tool_progress",
            "tool_key": tool_key,
            "phase": phase,
        }
        get_stream_writer()(payload)
