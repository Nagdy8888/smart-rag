"""Framework-neutral optional-tool progress reporting. No LangGraph imports."""

from __future__ import annotations

import logging
from typing import Literal, Protocol

LOGGER = logging.getLogger(__name__)

ToolProgressPhase = Literal["started", "completed", "failed"]


class ToolProgressReporter(Protocol):
    """Observe selected tool keys and execution phases.

    Implementations must not receive query text, arguments, results, or
    exception strings. Reporter failures must not change tool outcomes.
    """

    def selected(self, tool_keys: tuple[str, ...]) -> None:
        """Record the role-visible selected keys for this run.

        Args:
            tool_keys: Authorized catalog keys after policy filtering.
        """

    def phase(self, tool_key: str, phase: ToolProgressPhase) -> None:
        """Record one execution phase for a previously selected key.

        Args:
            tool_key: Catalog key from the selected tuple.
            phase: ``started``, ``completed``, or ``failed``.
        """


def report_selected(
    reporter: ToolProgressReporter | None, tool_keys: tuple[str, ...]
) -> None:
    """Notify selection after authorization. Ignore reporter failures.

    Args:
        reporter: Optional observer.
        tool_keys: Role-visible selected keys. Empty tuples are ignored.
    """

    if reporter is None or not tool_keys:
        return
    try:
        reporter.selected(tool_keys)
    except Exception:
        LOGGER.exception("optional_tool_progress_reporter_failed")


def report_phase(
    reporter: ToolProgressReporter | None,
    tool_key: str,
    phase: ToolProgressPhase,
) -> None:
    """Notify one execution phase. Ignore reporter failures.

    Args:
        reporter: Optional observer.
        tool_key: Selected catalog key.
        phase: Execution phase.
    """

    if reporter is None:
        return
    try:
        reporter.phase(tool_key, phase)
    except Exception:
        LOGGER.exception("optional_tool_progress_reporter_failed")
