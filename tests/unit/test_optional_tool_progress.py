"""Optional-tool progress reports selected keys and safe phases only."""

from __future__ import annotations

from pathlib import Path

import pytest
from smart_rag_agents.query.streaming.tool_progress import LangGraphToolProgressReporter
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.progress import ToolProgressPhase, report_phase
from smart_rag_core.tools.service import resolve_optional_tools

_MEMBER = "11111111-1111-4111-8111-111111111111"
_TABLE = "22222222-2222-4222-8222-222222222222"
_CORE_PROGRESS = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "tools"
    / "progress.py"
)


class _RecordingReporter:
    """Capture selected keys and phases without query or result text."""

    def __init__(self) -> None:
        """Create an empty recording."""

        self.events: list[object] = []

    def selected(self, tool_keys: tuple[str, ...]) -> None:
        """Record authorized keys.

        Args:
            tool_keys: Selected catalog keys.
        """

        self.events.append(("selected", tool_keys))

    def phase(self, tool_key: str, phase: ToolProgressPhase) -> None:
        """Record one phase.

        Args:
            tool_key: Selected catalog key.
            phase: Execution phase.
        """

        self.events.append((tool_key, phase))


def _caller(role: UserRole = UserRole.MEMBER) -> CallerContext:
    """Build a live caller for progress tests.

    Args:
        role: Live role.

    Returns:
        Frozen caller context.
    """

    return CallerContext(user_id=_MEMBER, role=role, authorization_version=1)


def test_intent_none_and_skipped_emit_no_phases() -> None:
    """Core questions and unauthorized viewers produce no progress."""

    none_reporter = _RecordingReporter()
    resolve_optional_tools(
        query="What is the status of INV-SR-1001?",
        caller=_caller(),
        remaining_tool_calls=4,
        remaining_discovery_rounds=1,
        remaining_manifests=3,
        remaining_side_effects=1,
        remaining_model_calls=7,
        progress=none_reporter,
    )
    skipped_reporter = _RecordingReporter()
    resolve_optional_tools(
        query="export the table as csv",
        caller=_caller(UserRole.VIEWER),
        remaining_tool_calls=4,
        remaining_discovery_rounds=1,
        remaining_manifests=3,
        remaining_side_effects=1,
        remaining_model_calls=6,
        progress=skipped_reporter,
    )
    assert none_reporter.events == []
    assert skipped_reporter.events == []


def test_selected_success_emits_started_then_completed() -> None:
    """One authorized export reports start then completion."""

    reporter = _RecordingReporter()
    mode, _prompt, keys, result, *_rest = resolve_optional_tools(
        query="export the table as csv",
        caller=_caller(),
        remaining_tool_calls=4,
        remaining_discovery_rounds=1,
        remaining_manifests=3,
        remaining_side_effects=1,
        remaining_model_calls=6,
        authorized_table_ids=(_TABLE,),
        progress=reporter,
    )
    assert keys == ("export_csv",)
    assert result is not None
    assert result.status == "ok"
    assert reporter.events == [
        ("selected", ("export_csv",)),
        ("export_csv", "started"),
        ("export_csv", "completed"),
    ]
    serialized = repr(reporter.events)
    assert "export the table" not in serialized
    assert "arguments" not in serialized
    assert "INV" not in serialized
    del mode


def test_safe_tool_failure_emits_started_then_failed() -> None:
    """Executor rejection after selection reports failed, not completed."""

    reporter = _RecordingReporter()
    with pytest.raises(ToolError, match="unauthorized_table"):
        resolve_optional_tools(
            query="export the table as csv",
            caller=_caller(),
            remaining_tool_calls=4,
            remaining_discovery_rounds=1,
            remaining_manifests=3,
            remaining_side_effects=1,
            remaining_model_calls=6,
            authorized_table_ids=(),
            progress=reporter,
        )
    assert reporter.events == [
        ("selected", ("export_csv",)),
        ("export_csv", "started"),
        ("export_csv", "failed"),
    ]


def test_reporter_failure_does_not_change_tool_outcome() -> None:
    """Observability exceptions are ignored so execution still succeeds."""

    class _Boom:
        """Raise on every callback."""

        def selected(self, tool_keys: tuple[str, ...]) -> None:
            """Fail selection.

            Args:
                tool_keys: Unused.
            """

            del tool_keys
            raise RuntimeError("reporter_boom")

        def phase(self, tool_key: str, phase: ToolProgressPhase) -> None:
            """Fail phase.

            Args:
                tool_key: Unused.
                phase: Unused.
            """

            del tool_key, phase
            raise RuntimeError("reporter_boom")

    _mode, _prompt, keys, result, *_rest = resolve_optional_tools(
        query="export the table as csv",
        caller=_caller(),
        remaining_tool_calls=4,
        remaining_discovery_rounds=1,
        remaining_manifests=3,
        remaining_side_effects=1,
        remaining_model_calls=6,
        authorized_table_ids=(_TABLE,),
        progress=_Boom(),
    )
    assert keys == ("export_csv",)
    assert result is not None
    assert result.status == "ok"


def test_adapter_rejects_unselected_keys_and_writes_safe_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The LangGraph adapter emits only kind, tool_key, and phase."""

    written: list[object] = []
    monkeypatch.setattr(
        "smart_rag_agents.query.streaming.tool_progress.get_stream_writer",
        lambda: written.append,
    )
    reporter = LangGraphToolProgressReporter()
    reporter.selected(("export_csv",))
    reporter.phase("export_csv", "started")
    reporter.phase("admin_user_invite", "started")
    assert written == [
        {"kind": "tool_progress", "tool_key": "export_csv", "phase": "started"}
    ]
    report_phase(reporter, "export_csv", "completed")
    assert written[-1] == {
        "kind": "tool_progress",
        "tool_key": "export_csv",
        "phase": "completed",
    }


def test_core_progress_module_has_no_langgraph_import() -> None:
    """Core progress stays framework-neutral."""

    body = _CORE_PROGRESS.read_text(encoding="utf-8")
    assert "langgraph" not in body
