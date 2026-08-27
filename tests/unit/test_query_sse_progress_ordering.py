"""Production v2 dispatch order, commit-before-map, and cancel-after-start."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from smart_rag_api.services.query_sse_mapping import QuerySseMapper
from smart_rag_api.services.sse.langgraph_stream_consume import (
    MappedStreamResult,
    iter_mapped_langgraph_updates,
)
from smart_rag_api.services.sse.stream_dispatch import production_astream_options
from smart_rag_core.query_answer.models import AnswerPayload

from tests.support.query_sse import runtime
from tests.unit.typed_attrs import ignore_args


def _v2(mode: str, data: object) -> dict[str, object]:
    """Build one observed LangGraph 1.2.11 v2 part.

    Args:
        mode: ``updates`` or ``custom``.
        data: Mode payload.

    Returns:
        StreamPart mapping.
    """

    return {"type": mode, "ns": (), "data": data}


def _answer(text: str) -> dict[str, object]:
    """Dump one complete answer payload.

    Args:
        text: Answer prose.

    Returns:
        JSON-ready mapping.
    """

    return AnswerPayload(answer_text=text, status="complete").model_dump(mode="json")


class _CommitConn:
    """Record commits that must happen before derived mapping."""

    def __init__(self) -> None:
        """Create an empty commit log."""

        self.events: list[str] = []

    def commit(self) -> None:
        """Record one database commit."""

        self.events.append("commit")


class _FakeStream:
    """Async iterator over stored v2 parts."""

    def __init__(self, parts: tuple[object, ...]) -> None:
        """Store parts.

        Args:
            parts: Ordered stream items.
        """

        self._parts = parts
        self._index = 0

    def __aiter__(self) -> _FakeStream:
        """Return this iterator.

        Returns:
            This stream.
        """

        return self

    async def __anext__(self) -> object:
        """Yield the next part.

        Returns:
            The next stored part.

        Raises:
            StopAsyncIteration: When exhausted.
        """

        if self._index >= len(self._parts):
            raise StopAsyncIteration
        item = self._parts[self._index]
        self._index += 1
        return item


def test_production_astream_options_are_v2_multi_mode() -> None:
    """Production requests updates+custom version v2."""

    assert production_astream_options() == {
        "stream_mode": ["updates", "custom"],
        "version": "v2",
    }
    runtime = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "apps"
        / "backend"
        / "src"
        / "smart_rag_api"
        / "services"
        / "sse"
        / "langgraph_runtime.py"
    ).read_text(encoding="utf-8")
    assert "production_astream_options()" in runtime
    assert 'stream_mode="updates"' not in runtime


async def _collect(
    parts: tuple[object, ...],
    *,
    cancel: asyncio.Event | None = None,
    conn: _CommitConn | None = None,
) -> tuple[list[tuple[str, dict[str, object]]], _CommitConn]:
    """Drain mapped drafts from one fake v2 stream.

    Args:
        parts: Stream parts.
        cancel: Optional cancel event.
        conn: Optional commit recorder.

    Returns:
        Drafts and the commit recorder.
    """

    connection = conn or _CommitConn()
    mapper = QuerySseMapper()
    drafts: list[tuple[str, dict[str, object]]] = []
    async for item in iter_mapped_langgraph_updates(
        stream_iter=_FakeStream(parts),
        mapper=mapper,
        context=runtime(),
        settings=SimpleNamespace(),
        cancel_event=cancel or asyncio.Event(),
        connection=connection,
        commit_successful_terminal=ignore_args,
        set_termination=ignore_args,
        last_remaining_calls=8,
        last_status="running",
    ):
        if isinstance(item, MappedStreamResult):
            continue
        drafts.append(item)
        connection.events.append(f"yield:{item[0]}")
    return drafts, connection


def test_required_progress_order_and_commit_before_each_part() -> None:
    """Starts, tools, completions, verify, token_delta, one terminal."""

    parts = (
        _v2("custom", {"kind": "node_start", "stage": "generate_answer"}),
        _v2(
            "custom",
            {"kind": "tool_progress", "tool_key": "export_csv", "phase": "started"},
        ),
        _v2(
            "custom",
            {"kind": "tool_progress", "tool_key": "export_csv", "phase": "completed"},
        ),
        _v2(
            "updates",
            {
                "generate_answer": {
                    "status": "drafted",
                    "answer": _answer("SECRET_DRAFT"),
                }
            },
        ),
        _v2("custom", {"kind": "node_start", "stage": "verify_answer"}),
        _v2(
            "updates",
            {
                "verify_answer": {
                    "status": "verified",
                    "answer": _answer("PUBLIC_FINAL"),
                }
            },
        ),
    )
    drafts, conn = asyncio.run(_collect(parts))
    types = [item[0] for item in drafts]
    assert types.index("token_delta") > types.index("status")
    assert types.count("completed") == 1
    assert "SECRET_DRAFT" not in str(drafts)
    assert any(
        item[0] == "token_delta" and item[1].get("delta") == "PUBLIC_FINAL"
        for item in drafts
    )
    started = [
        item[1]
        for item in drafts
        if item[0] == "status" and item[1].get("phase") == "started"
    ]
    completed = [
        item[1]
        for item in drafts
        if item[0] == "status" and item[1].get("phase") == "completed"
    ]
    tools = [item for item in drafts if item[0] == "tool_progress"]
    assert [item["stage"] for item in started] == [
        "generate_answer",
        "verify_answer",
    ]
    assert completed[0]["stage"] == "generate_answer"
    assert completed[-1]["stage"] == "verify_answer"
    assert [item[1]["phase"] for item in tools] == ["started", "completed"]
    assert conn.events[0] == "commit"
    assert conn.events.count("commit") == len(parts)
    first_generate_start = next(
        index for index, event in enumerate(conn.events) if event == "yield:status"
    )
    assert conn.events[first_generate_start - 1] == "commit"


def test_cancel_after_started_does_not_fabricate_completed() -> None:
    """Cancel after a start persists the start and no success terminal."""

    parts = (
        _v2("custom", {"kind": "node_start", "stage": "prepare_query"}),
        _v2("updates", {"prepare_query": {"status": "prepared"}}),
    )
    cancel = asyncio.Event()

    async def _run() -> list[str]:
        """Set cancel after the first draft.

        Returns:
            Event types.
        """

        connection = _CommitConn()
        mapper = QuerySseMapper()
        types: list[str] = []
        async for item in iter_mapped_langgraph_updates(
            stream_iter=_FakeStream(parts),
            mapper=mapper,
            context=runtime(),
            settings=SimpleNamespace(),
            cancel_event=cancel,
            connection=connection,
            commit_successful_terminal=ignore_args,
            set_termination=ignore_args,
            last_remaining_calls=8,
            last_status="running",
        ):
            if isinstance(item, MappedStreamResult):
                continue
            types.append(item[0])
            if item[0] == "status" and item[1].get("phase") == "started":
                cancel.set()
        return types

    types = asyncio.run(_run())
    assert "status" in types
    assert "completed" not in types
    assert "token_delta" not in types


def test_reconnect_replay_does_not_call_astream(monkeypatch: Any) -> None:
    """A second attach after a finished run must not open another astream."""

    from smart_rag_api.services.sse_stream import (
        LangGraphQueryRunExecutor,
        QueryRunRegistry,
        SseStreamService,
    )
    from smart_rag_core.sse.store import MemoryRunEventStore

    from tests.support.query_sse import (
        RecordingAsyncStream,
        RecordingCompiled,
        patch_recording_executor,
        verified_chunk,
    )
    from tests.support.query_sse import (
        caller as make_caller,
    )

    stream = RecordingAsyncStream((verified_chunk("VISIBLE_FINAL"),))
    compiled = RecordingCompiled(stream)
    calls = {"astream": 0}
    real_astream = compiled.astream

    def _count(*args: object, **kwargs: object) -> object:
        """Count production astream openings.

        Args:
            *args: Graph input.
            **kwargs: Stream options.

        Returns:
            The recording stream.
        """

        calls["astream"] += 1
        return real_astream(*args, **kwargs)

    compiled.astream = _count  # type: ignore[method-assign]
    executor = LangGraphQueryRunExecutor()
    patch_recording_executor(monkeypatch, executor, compiled)
    store = MemoryRunEventStore()
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=executor,
        sse_schema_version="1",
    )
    owner = make_caller()
    context = runtime()
    service.remember_admitted(owner, context, message="hello")

    async def _first_then_replay() -> list[str]:
        """Drain the live run, then replay without a new executor.

        Returns:
            Replayed event types.
        """

        live_types: list[str] = []
        async for frame in service.iter_frames(
            owner, run_id=context.run_id, after=0, context=context
        ):
            if "event: completed" in frame:
                live_types.append("completed")
        assert live_types == ["completed"]
        assert calls["astream"] == 1
        replayed: list[str] = []
        async for frame in service.iter_frames(
            owner, run_id=context.run_id, after=0, context=context
        ):
            if "event: completed" in frame:
                replayed.append("completed")
        return replayed

    replayed = asyncio.run(_first_then_replay())
    assert replayed == ["completed"]
    assert calls["astream"] == 1
