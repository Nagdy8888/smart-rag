"""SSE stream drain, cancel, disconnect, compile reuse, and heartbeats."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

from smart_rag_api.services.sse_stream import (
    FixtureQueryRunExecutor,
    LangGraphQueryRunExecutor,
    QueryRunRegistry,
    SseStreamService,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.sse.store import MemoryRunEventStore

from tests.support.query_sse import (
    RecordingAsyncStream,
    RecordingCompiled,
    empty_verified_chunk,
    patch_recording_executor,
    trailing_chunk,
    verified_chunk,
)
from tests.support.query_sse import (
    caller as make_caller,
)
from tests.support.query_sse import (
    runtime as make_runtime,
)
from tests.unit.typed_attrs import set_attr, typed_attr


def test_successful_stream_drains_and_skips_aclose(monkeypatch: Any) -> None:
    """A terminal plus trailing chunk exhausts naturally without aclose."""

    stream = RecordingAsyncStream((verified_chunk("VISIBLE_FINAL"), trailing_chunk()))
    executor = LangGraphQueryRunExecutor()
    commits, settlements = patch_recording_executor(
        monkeypatch, executor, RecordingCompiled(stream)
    )

    async def _collect() -> list[str]:
        """Drain executor event types.

        Returns:
            Event type names.
        """

        events: list[str] = []
        async for event_type, _payload in executor.execute(
            context=make_runtime(),
            message="hello",
            cancel_event=asyncio.Event(),
        ):
            events.append(event_type)
        return events

    types = asyncio.run(_collect())
    assert stream.consumed == 2
    assert stream.aclose_count == 0
    assert types.count("completed") == 1
    assert executor.termination_summary["termination_reason"] == "completed"
    assert executor.termination_summary["stream_exhausted"] is True
    assert settlements == ["persist"]
    assert commits.count("close") == 1


def test_mid_stream_cancel_closes_once(monkeypatch: Any) -> None:
    """Cancel after the first yield closes the unfinished stream once."""

    stream = RecordingAsyncStream(
        (
            {
                "generate_answer": {
                    "status": "drafted",
                    "answer": AnswerPayload(
                        answer_text="draft", status="complete"
                    ).model_dump(mode="json"),
                }
            },
            verified_chunk("later"),
            trailing_chunk(),
        )
    )
    executor = LangGraphQueryRunExecutor()
    _commits, settlements = patch_recording_executor(
        monkeypatch, executor, RecordingCompiled(stream)
    )

    async def _collect() -> list[str]:
        """Cancel after the first status event.

        Returns:
            Event type names.
        """

        events: list[str] = []
        cancel = asyncio.Event()
        async for event_type, _payload in executor.execute(
            context=make_runtime(),
            message="hello",
            cancel_event=cancel,
        ):
            events.append(event_type)
            cancel.set()
        return events

    types = asyncio.run(_collect())
    assert "completed" not in types
    assert stream.aclose_count == 1
    assert stream.consumed < 3
    assert settlements == []
    assert executor.termination_summary["termination_reason"] == "cancelled"
    assert executor.termination_summary["stream_exhausted"] is False


def test_graph_error_is_one_error_terminal(monkeypatch: Any) -> None:
    """A natural empty verified answer is one error and no success settlement."""

    stream = RecordingAsyncStream((empty_verified_chunk(), trailing_chunk()))
    executor = LangGraphQueryRunExecutor()
    summarize_calls: list[str] = []
    _commits, settlements = patch_recording_executor(
        monkeypatch, executor, RecordingCompiled(stream)
    )

    def _record_summary(*args: object, **kwargs: object) -> None:
        """Record an unexpected successful-settlement summary.

        Args:
            *args: Unused summarize arguments.
            **kwargs: Unused summarize options.
        """

        del args, kwargs
        summarize_calls.append("summary")

    monkeypatch.setattr(executor, "_maybe_summarize", _record_summary)

    async def _collect() -> list[str]:
        """Drain error-terminal events.

        Returns:
            Event type names.
        """

        events: list[str] = []
        async for event_type, _payload in executor.execute(
            context=make_runtime(),
            message="hello",
            cancel_event=asyncio.Event(),
        ):
            events.append(event_type)
        return events

    types = asyncio.run(_collect())
    assert types.count("error") == 1
    assert "completed" not in types
    assert summarize_calls == []
    assert settlements == []
    assert stream.consumed == 2
    assert stream.aclose_count == 0
    assert executor.termination_summary["termination_reason"] == "error"


def test_consumer_disconnect_leaves_executor_resumable() -> None:
    """Closing the HTTP consumer does not cancel a still-running executor."""

    store = MemoryRunEventStore()
    registry = QueryRunRegistry()
    executor = FixtureQueryRunExecutor(hold_seconds=0.4, emit_completed=True)
    service = SseStreamService(
        store=store,
        registry=registry,
        executor=executor,
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _disconnect_then_resume() -> list[str]:
        """Close the first attach, then resume remaining events.

        Returns:
            Event types from the resume attach.
        """

        agen = service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        )
        first = await agen.__anext__()
        assert "event:" in first
        close = getattr(agen, "aclose", None)
        assert callable(close)
        closed = close()
        if inspect.isawaitable(closed):
            await closed
        handle = registry.get(runtime.run_id)
        assert handle is not None
        assert handle.executor_task is not None
        assert handle.executor_task.done() is False
        await handle.executor_task
        types: list[str] = []
        async for frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            if "event: completed" in frame:
                types.append("completed")
            if "event: cancelled" in frame:
                types.append("cancelled")
        return types

    types = asyncio.run(_disconnect_then_resume())
    assert "completed" in types
    assert "cancelled" not in types


def test_cancel_grace_hard_cancels_lingering_task() -> None:
    """Explicit cancel waits briefly, then hard-cancels a stuck executor."""

    store = MemoryRunEventStore()
    registry = QueryRunRegistry()
    service = SseStreamService(
        store=store,
        registry=registry,
        executor=FixtureQueryRunExecutor(),
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")
    live = registry.get_or_create(runtime.run_id)
    live.started = True

    async def _stuck() -> None:
        """Ignore cooperative cancel and sleep past the grace window."""

        await asyncio.sleep(2)

    async def _run() -> bool:
        """Request cancel and wait for the grace hard-cancel.

        Returns:
            True when the stuck task finished after the grace window.
        """

        task = asyncio.create_task(_stuck())
        live.executor_task = task
        service.notify_cancel(caller, run_id=runtime.run_id)
        await asyncio.sleep(0.05)
        still_running = not task.done()
        await asyncio.sleep(0.35)
        finished = task.done()
        return still_running and finished

    assert asyncio.run(_run()) is True


def test_executor_compiles_once_per_checkpointer(monkeypatch: Any) -> None:
    """Static topology compiles once across two execute() calls."""

    compiled = RecordingCompiled(RecordingAsyncStream((verified_chunk("ONE"),)))
    executor = LangGraphQueryRunExecutor()
    patch_recording_executor(monkeypatch, executor, compiled)

    async def _twice() -> None:
        """Run two execute() loops on one executor."""

        cancel = asyncio.Event()
        async for _event in executor.execute(
            context=make_runtime(), message="one", cancel_event=cancel
        ):
            pass
        set_attr(compiled, "_stream", RecordingAsyncStream((verified_chunk("TWO"),)))
        async for _event in executor.execute(
            context=make_runtime(), message="two", cancel_event=cancel
        ):
            pass

    asyncio.run(_twice())
    assert executor.compile_count == 1


def test_one_heartbeat_writer_and_none_after_terminal() -> None:
    """Only ``_run_heartbeat`` appends beats, and none after a terminal."""

    store = MemoryRunEventStore()
    registry = QueryRunRegistry()
    service = SseStreamService(
        store=store,
        registry=registry,
        executor=FixtureQueryRunExecutor(hold_seconds=1.0, emit_completed=False),
        sse_schema_version="1",
        heartbeat_interval_seconds=0.05,
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _hold() -> int:
        """Attach briefly, then cancel and prove heartbeats stop.

        Returns:
            Heartbeat count observed before cancel.
        """

        agen = service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        )
        await agen.__anext__()
        await asyncio.sleep(0.22)
        before = [
            item
            for item in store.list_after(caller, run_id=runtime.run_id, after=0)
            if item.event_type == "heartbeat"
        ]
        service.notify_cancel(caller, run_id=runtime.run_id)
        await asyncio.sleep(0.16)
        after = [
            item
            for item in store.list_after(caller, run_id=runtime.run_id, after=0)
            if item.event_type == "heartbeat"
        ]
        close = getattr(agen, "aclose", None)
        if callable(close):
            closed = close()
            if inspect.isawaitable(closed):
                await closed
        assert after == before
        return len(before)

    count = asyncio.run(_hold())
    assert 1 <= count <= 6


def test_graph_chunk_is_parsed_once(monkeypatch: Any) -> None:
    """Usage accounting and the SSE mapper share one normalized chunk."""

    parses: list[object] = []
    from smart_rag_api.services.sse import stream_parts as parts_mod

    real = parts_mod.parse_stream_part

    def _count(raw_chunk: object) -> object:
        """Count one parse then delegate.

        Args:
            raw_chunk: LangGraph stream part.

        Returns:
            Parsed part, or None.
        """

        parses.append(raw_chunk)
        return real(raw_chunk)

    monkeypatch.setattr(
        "smart_rag_api.services.sse.stream_dispatch.parse_stream_part",
        _count,
    )
    stream = RecordingAsyncStream((verified_chunk("ONCE"),))
    executor = LangGraphQueryRunExecutor()
    patch_recording_executor(monkeypatch, executor, RecordingCompiled(stream))

    async def _drain() -> None:
        """Consume the patched executor."""

        async for _event in executor.execute(
            context=make_runtime(),
            message="hello",
            cancel_event=asyncio.Event(),
        ):
            pass

    asyncio.run(_drain())
    assert len(parses) == 1


class _BlockingAppendStore(MemoryRunEventStore):
    """Memory store that holds the caller thread during append."""

    def __init__(self, hold_seconds: float, started: threading.Event) -> None:
        """Configure the blocking append.

        Args:
            hold_seconds: Sleep duration on the worker thread.
            started: Set when the blocking sleep begins.
        """

        super().__init__()
        self.hold_seconds = hold_seconds
        self.started = started

    def append(
        self,
        caller: Any,
        *,
        run_id: Any,
        event_type: str,
        payload: dict[str, object],
    ) -> Any:
        """Block this thread, then persist.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted event from the memory store.
        """

        self.started.set()
        time.sleep(self.hold_seconds)
        return super().append(
            caller, run_id=run_id, event_type=event_type, payload=payload
        )


def test_append_async_keeps_event_loop_responsive() -> None:
    """A blocking store append cannot freeze the asyncio loop."""

    started = threading.Event()
    store = _BlockingAppendStore(0.25, started)
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=FixtureQueryRunExecutor(),
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _probe() -> float:
        """Start a blocking append and tick the loop while it holds.

        Returns:
            Seconds the loop stayed able to sleep during the append.
        """

        append_task = asyncio.create_task(
            typed_attr(service, "_append_async")(
                caller,
                runtime.run_id,
                "status",
                {"stage": "admitted", "status": "running"},
            )
        )
        while not started.is_set():
            await asyncio.sleep(0)
        ticked = time.monotonic()
        await asyncio.sleep(0.05)
        elapsed = time.monotonic() - ticked
        persisted = await append_task
        assert persisted is not None
        assert persisted.event_type == "status"
        return elapsed

    assert asyncio.run(_probe()) < 0.2


class _LockTimeoutStore(MemoryRunEventStore):
    """Memory store that raises a lock-timeout admission error."""

    def append(
        self,
        caller: Any,
        *,
        run_id: Any,
        event_type: str,
        payload: dict[str, object],
    ) -> Any:
        """Raise a lock timeout with a SQLSTATE cause.

        Args:
            caller: Unused.
            run_id: Unused.
            event_type: Unused.
            payload: Unused. Must not appear in logs.

        Raises:
            QueryAdmissionError: Always ``lock_timeout``.
        """

        del caller, run_id, event_type, payload
        cause = Exception(
            "canceling statement due to lock timeout "
            "postgresql://user:secret@example.invalid/db"
        )
        cause.sqlstate = "55P03"  # type: ignore[attr-defined]
        raise QueryAdmissionError("lock_timeout") from cause


def test_append_lock_failure_logs_sanitized_fields(
    caplog: Any,
) -> None:
    """Lock failures log run id, type, SQLSTATE, and duration only."""

    store = _LockTimeoutStore()
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=FixtureQueryRunExecutor(),
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")
    with caplog.at_level(
        logging.INFO, logger="smart_rag_api.services.sse.event_append"
    ):
        persisted = typed_attr(service, "_append")(
            caller,
            runtime.run_id,
            "heartbeat",
            {},
        )
    assert persisted is None
    records = [
        item
        for item in caplog.records
        if getattr(item, "event", None) == "sse.append_failed"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.run_id == str(runtime.run_id)
    assert record.sse_event_type == "heartbeat"
    assert record.reason == "lock_timeout"
    assert record.sqlstate == "55P03"
    assert isinstance(record.elapsed_seconds, float)
    extras = {
        key: getattr(record, key)
        for key in (
            "event",
            "run_id",
            "sse_event_type",
            "reason",
            "sqlstate",
            "elapsed_seconds",
        )
    }
    rendered = record.getMessage() + str(extras)
    assert "postgresql://" not in rendered
    assert "secret" not in rendered
    assert "example.invalid" not in rendered


def test_live_run_wait_appended_timeout_and_notify() -> None:
    """``wait_appended`` returns on timeout, on notify, and when already newer."""

    from smart_rag_api.services.sse.registry import LiveQueryRun

    async def _run() -> tuple[int, int, float, int]:
        """Wait with no notify, then with a notify, then with a stale seen.

        Returns:
            Generation after timeout, after notify, seconds waited for the
            notify, and generation for an already-newer ``seen``.
        """

        live = LiveQueryRun()
        timed_out = await live.wait_appended(0, 0.05)
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, live.notify_appended)
        started = time.monotonic()
        notified = await live.wait_appended(0, 2.0)
        waited = time.monotonic() - started
        immediate = await live.wait_appended(0, 5.0)
        return timed_out, notified, waited, immediate

    timed_out, notified, waited, immediate = asyncio.run(_run())
    assert timed_out == 0
    assert notified == 1
    assert waited < 1.0
    assert immediate == 1


class _SlowListStore(MemoryRunEventStore):
    """Memory store whose replay read blocks the calling thread."""

    def __init__(self, hold_seconds: float) -> None:
        """Configure the blocking read.

        Args:
            hold_seconds: Sleep per ``list_after`` call.
        """

        super().__init__()
        self.hold_seconds = hold_seconds

    def list_after(self, caller: Any, *, run_id: Any, after: int) -> Any:
        """Block this thread, then read.

        Args:
            caller: Owner.
            run_id: Run id.
            after: Exclusive cursor.

        Returns:
            Events from the memory store.
        """

        time.sleep(self.hold_seconds)
        return super().list_after(caller, run_id=run_id, after=after)


def test_replay_list_after_runs_off_event_loop() -> None:
    """A slow replay read cannot freeze the asyncio loop."""

    store = _SlowListStore(0.2)
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=FixtureQueryRunExecutor(),
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _probe() -> int:
        """Tick every 10 ms while one replay read blocks its thread.

        Returns:
            Ticks counted during the replay.
        """

        ticks = 0

        async def _ticker() -> None:
            """Count loop turns until cancelled."""

            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker = asyncio.create_task(_ticker())
        async for _item in typed_attr(service, "_replay")(caller, runtime.run_id, 0):
            pass
        ticker.cancel()
        return ticks

    assert asyncio.run(_probe()) >= 8


class _SpacedExecutor:
    """Executor that yields status events with a fixed gap, then completes."""

    def __init__(self, count: int, gap_seconds: float) -> None:
        """Configure the spaced stream.

        Args:
            count: Status events before ``completed``.
            gap_seconds: Sleep before each status event.
        """

        self.count = count
        self.gap_seconds = gap_seconds
        self.start_count = 0

    async def execute(
        self,
        *,
        context: Any,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Yield spaced status events, then ``completed``.

        Args:
            context: Unused authorized context.
            message: Unused user text.
            cancel_event: Unused cancel flag.

        Yields:
            Catalog drafts.
        """

        del context, message, cancel_event
        self.start_count += 1
        for index in range(self.count):
            await asyncio.sleep(self.gap_seconds)
            yield ("status", {"stage": f"stage_{index}", "status": "running"})
        yield ("completed", {})


def test_attach_wakes_on_append_not_idle_poll(monkeypatch: Any) -> None:
    """Frames for a live run arrive on append, not after the idle poll."""

    monkeypatch.setattr(
        "smart_rag_api.services.sse.service.ATTACH_IDLE_POLL_SECONDS", 5.0
    )
    service = SseStreamService(
        store=MemoryRunEventStore(),
        registry=QueryRunRegistry(),
        executor=_SpacedExecutor(count=4, gap_seconds=0.05),
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _drain() -> tuple[list[str], float]:
        """Attach once and read every frame through the terminal.

        Returns:
            ``event:`` lines and elapsed seconds.
        """

        started = time.monotonic()
        lines: list[str] = []
        async for frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            lines.extend(
                line for line in frame.splitlines() if line.startswith("event:")
            )
        return lines, time.monotonic() - started

    lines, elapsed = asyncio.run(_drain())
    assert lines[-1] == "event: completed"
    assert lines.count("event: status") == 4
    assert elapsed < 1.5


def test_start_once_is_single_under_concurrent_attach() -> None:
    """Two attaches racing on one pending run start one executor."""

    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor(hold_seconds=0.1, emit_completed=True)
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=executor,
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _attach() -> list[str]:
        """Read one attach to its terminal.

        Returns:
            Frames from this attach.
        """

        return [
            frame
            async for frame in service.iter_frames(
                caller, run_id=runtime.run_id, after=0, context=runtime
            )
        ]

    async def _both() -> list[list[str]]:
        """Run two attaches at once.

        Returns:
            Frames from each attach.
        """

        return list(await asyncio.gather(_attach(), _attach()))

    first, second = asyncio.run(_both())
    schema_rows = [
        item
        for item in store.list_after(caller, run_id=runtime.run_id, after=0)
        if item.event_type == "schema"
    ]
    assert executor.start_count == 1
    assert len(schema_rows) == 1
    assert any("event: completed" in frame for frame in first)
    assert any("event: completed" in frame for frame in second)


def test_stream_commits_and_terminal_persist_run_off_event_loop(
    monkeypatch: Any,
) -> None:
    """Run-connection open, commits, and post-terminal persist use threads."""

    stream = RecordingAsyncStream((verified_chunk("THREAD"), trailing_chunk()))
    executor = LangGraphQueryRunExecutor()
    patch_recording_executor(monkeypatch, executor, RecordingCompiled(stream))
    loop_threads: list[int] = []
    open_threads: list[int] = []
    commit_threads: list[int] = []
    persist_threads: list[int] = []

    def _open_connection(dsn: object) -> Any:
        """Return a connection whose commit records its thread.

        Args:
            dsn: Unused DSN.

        Returns:
            Connection stand-in.
        """

        del dsn
        open_threads.append(threading.get_ident())

        def _commit() -> None:
            """Record the committing thread."""

            commit_threads.append(threading.get_ident())

        def _close() -> None:
            """Accept close."""

        return SimpleNamespace(commit=_commit, close=_close)

    def _persist(*args: object, **kwargs: object) -> None:
        """Record the persisting thread.

        Args:
            *args: Unused persist arguments.
            **kwargs: Unused persist options.
        """

        del args, kwargs
        persist_threads.append(threading.get_ident())

    monkeypatch.setattr(
        "smart_rag_api.services.query_graph_runtime.open_run_app_api_connection",
        _open_connection,
    )
    monkeypatch.setattr(executor, "_persist_assistant_answer", _persist)

    async def _drain() -> None:
        """Consume the patched executor and record the loop thread."""

        loop_threads.append(threading.get_ident())
        async for _event in executor.execute(
            context=make_runtime(),
            message="hello",
            cancel_event=asyncio.Event(),
        ):
            pass

    asyncio.run(_drain())
    assert open_threads
    assert commit_threads
    assert persist_threads
    assert loop_threads[0] not in open_threads
    assert loop_threads[0] not in commit_threads
    assert loop_threads[0] not in persist_threads


class _TimedExecutor:
    """Executor that records when each yielded draft is handed back."""

    def __init__(self, count: int) -> None:
        """Configure the stream.

        Args:
            count: Status drafts before ``completed``.
        """

        self.count = count
        self.resumed_at: list[float] = []

    async def execute(
        self,
        *,
        context: Any,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Yield status drafts without delay, then ``completed``.

        Args:
            context: Unused authorized context.
            message: Unused user text.
            cancel_event: Unused cancel flag.

        Yields:
            Catalog drafts.
        """

        del context, message, cancel_event
        for index in range(self.count):
            yield ("status", {"stage": f"stage_{index}", "status": "running"})
            self.resumed_at.append(time.monotonic())
        yield ("completed", {})


def test_executor_does_not_wait_for_non_terminal_appends() -> None:
    """Five status drafts are handed back before their slow appends finish."""

    store = _BlockingAppendStore(0.1, threading.Event())
    executor = _TimedExecutor(count=5)
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=executor,
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _drain() -> list[str]:
        """Attach once and read every frame through the terminal.

        Returns:
            ``event:`` lines in stream order.
        """

        lines: list[str] = []
        async for frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            lines.extend(
                line for line in frame.splitlines() if line.startswith("event:")
            )
        return lines

    lines = asyncio.run(_drain())
    assert lines.count("event: status") == 5
    assert lines[-1] == "event: completed"
    assert executor.resumed_at[4] - executor.resumed_at[0] < 0.1
    events = store.list_after(caller, run_id=runtime.run_id, after=0)
    stages = [
        event.payload.get("stage") for event in events if event.event_type == "status"
    ]
    assert stages == [f"stage_{index}" for index in range(5)]
    assert events[-1].event_type == "completed"


class _TerminalProbeExecutor:
    """Executor that checks, after ``completed``, whether it is persisted."""

    def __init__(self, store: MemoryRunEventStore, caller: Any, run_id: Any) -> None:
        """Keep the store handle used for the check.

        Args:
            store: Event store the service writes to.
            caller: Run owner.
            run_id: Run id.
        """

        self.store = store
        self.caller = caller
        self.run_id = run_id
        self.completed_persisted: bool | None = None

    async def execute(
        self,
        *,
        context: Any,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Yield status and ``completed``, then record what is persisted.

        Args:
            context: Unused authorized context.
            message: Unused user text.
            cancel_event: Unused cancel flag.

        Yields:
            Catalog drafts.
        """

        del context, message, cancel_event
        yield ("status", {"stage": "admitted", "status": "running"})
        yield ("completed", {})
        events = self.store.list_after(self.caller, run_id=self.run_id, after=0)
        self.completed_persisted = any(
            event.event_type == "completed" for event in events
        )


def test_terminal_flush_precedes_post_terminal_work() -> None:
    """Code after ``yield completed`` sees the terminal already persisted."""

    store = _BlockingAppendStore(0.05, threading.Event())
    caller = make_caller()
    runtime = make_runtime()
    executor = _TerminalProbeExecutor(store, caller, runtime.run_id)
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=executor,
        sse_schema_version="1",
    )
    service.remember_admitted(caller, runtime, message="hello")

    async def _drain() -> None:
        """Attach through the terminal, then wait for the executor check."""

        async for _frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            pass
        for _ in range(100):
            if executor.completed_persisted is not None:
                return
            await asyncio.sleep(0.01)

    asyncio.run(_drain())
    assert executor.completed_persisted is True


class _CancelWaitExecutor:
    """Executor that yields status drafts at once, then waits for cancel."""

    def __init__(self, count: int) -> None:
        """Configure the stream.

        Args:
            count: Status drafts yielded before waiting.
        """

        self.count = count

    async def execute(
        self,
        *,
        context: Any,
        message: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict[str, object]]]:
        """Yield status drafts, then end when cancel is requested.

        Args:
            context: Unused authorized context.
            message: Unused user text.
            cancel_event: Ends the stream when set.

        Yields:
            Catalog drafts.
        """

        del context, message
        for index in range(self.count):
            yield ("status", {"stage": f"stage_{index}", "status": "running"})
        await cancel_event.wait()


def test_cancel_skips_queued_drafts_and_keeps_one_terminal() -> None:
    """Cancel keeps one ``cancelled`` and skips queued status drafts."""

    store = _BlockingAppendStore(0.1, threading.Event())
    registry = QueryRunRegistry()
    service = SseStreamService(
        store=store,
        registry=registry,
        executor=_CancelWaitExecutor(count=5),
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _run() -> None:
        """Start the run, cancel after the first status row, then wait."""

        agen = service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        )
        await agen.__anext__()
        for _ in range(200):
            rows = store.list_after(caller, run_id=runtime.run_id, after=0)
            if any(row.event_type == "status" for row in rows):
                break
            await asyncio.sleep(0.01)
        live = registry.get(runtime.run_id)
        assert live is not None
        executor_task = live.executor_task
        assert executor_task is not None
        service.notify_cancel(caller, run_id=runtime.run_id)
        try:
            await asyncio.wait_for(executor_task, timeout=3.0)
        except asyncio.CancelledError:
            pass
        close = getattr(agen, "aclose", None)
        if callable(close):
            closed = close()
            if inspect.isawaitable(closed):
                await closed

    asyncio.run(_run())
    types = [
        row.event_type
        for row in store.list_after(caller, run_id=runtime.run_id, after=0)
    ]
    assert types.count("cancelled") == 1
    assert types.count("completed") + types.count("error") == 0
    assert types.count("status") <= 2
    assert len(types) - types.index("cancelled") - 1 <= 1


class _FailingStatusStore(MemoryRunEventStore):
    """Memory store whose append raises for the status stage ``boom``."""

    def append(
        self,
        caller: Any,
        *,
        run_id: Any,
        event_type: str,
        payload: dict[str, object],
    ) -> Any:
        """Raise for stage ``boom``, otherwise persist.

        Args:
            caller: Owner.
            run_id: Run id.
            event_type: Allow-listed type.
            payload: Candidate payload.

        Returns:
            Persisted event from the memory store.

        Raises:
            RuntimeError: For the ``boom`` status draft.
        """

        if event_type == "status" and payload.get("stage") == "boom":
            raise RuntimeError("store exploded")
        return super().append(
            caller, run_id=run_id, event_type=event_type, payload=payload
        )


def test_writer_failure_becomes_single_error_terminal() -> None:
    """An unexpected append failure ends the run with one sanitized error."""

    store = _FailingStatusStore()
    service = SseStreamService(
        store=store,
        registry=QueryRunRegistry(),
        executor=FixtureQueryRunExecutor(
            extra_events=(
                ("status", {"stage": "boom", "status": "running"}),
                ("status", {"stage": "after", "status": "running"}),
            ),
        ),
        sse_schema_version="1",
    )
    caller = make_caller()
    runtime = make_runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _drain() -> list[str]:
        """Attach once and read every frame through the terminal.

        Returns:
            ``event:`` lines in stream order.
        """

        lines: list[str] = []
        async for frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            lines.extend(
                line for line in frame.splitlines() if line.startswith("event:")
            )
        return lines

    lines = asyncio.run(_drain())
    assert lines[-1] == "event: error"
    events = store.list_after(caller, run_id=runtime.run_id, after=0)
    types = [event.event_type for event in events]
    stages = [
        event.payload.get("stage") for event in events if event.event_type == "status"
    ]
    assert types.count("error") == 1
    assert "completed" not in types
    assert "boom" not in stages
    assert "after" not in stages
