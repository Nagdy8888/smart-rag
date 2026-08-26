"""SSE stream drain, cancel, disconnect, compile reuse, and heartbeats."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
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
    _caller,
    _empty_verified_chunk,
    _patch_recording_executor,
    _RecordingAsyncStream,
    _RecordingCompiled,
    _runtime,
    _trailing_chunk,
    _verified_chunk,
)


def test_successful_stream_drains_and_skips_aclose(monkeypatch: Any) -> None:
    """A terminal plus trailing chunk exhausts naturally without aclose."""

    stream = _RecordingAsyncStream(
        (_verified_chunk("VISIBLE_FINAL"), _trailing_chunk())
    )
    executor = LangGraphQueryRunExecutor()
    commits, settlements = _patch_recording_executor(
        monkeypatch, executor, _RecordingCompiled(stream)
    )

    async def _collect() -> list[str]:
        """Drain executor event types.

        Returns:
            Event type names.
        """

        events: list[str] = []
        async for event_type, _payload in executor.execute(
            context=_runtime(),
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

    stream = _RecordingAsyncStream(
        (
            {
                "generate_answer": {
                    "status": "drafted",
                    "answer": AnswerPayload(
                        answer_text="draft", status="complete"
                    ).model_dump(mode="json"),
                }
            },
            _verified_chunk("later"),
            _trailing_chunk(),
        )
    )
    executor = LangGraphQueryRunExecutor()
    _commits, settlements = _patch_recording_executor(
        monkeypatch, executor, _RecordingCompiled(stream)
    )

    async def _collect() -> list[str]:
        """Cancel after the first status event.

        Returns:
            Event type names.
        """

        events: list[str] = []
        cancel = asyncio.Event()
        async for event_type, _payload in executor.execute(
            context=_runtime(),
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

    stream = _RecordingAsyncStream((_empty_verified_chunk(), _trailing_chunk()))
    executor = LangGraphQueryRunExecutor()
    summarize_calls: list[str] = []
    _commits, settlements = _patch_recording_executor(
        monkeypatch, executor, _RecordingCompiled(stream)
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
            context=_runtime(),
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
    caller = _caller()
    runtime = _runtime()
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
    caller = _caller()
    runtime = _runtime()
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

    compiled = _RecordingCompiled(_RecordingAsyncStream((_verified_chunk("ONE"),)))
    executor = LangGraphQueryRunExecutor()
    _patch_recording_executor(monkeypatch, executor, compiled)

    async def _twice() -> None:
        """Run two execute() loops on one executor."""

        cancel = asyncio.Event()
        async for _event in executor.execute(
            context=_runtime(), message="one", cancel_event=cancel
        ):
            pass
        compiled.stream = _RecordingAsyncStream((_verified_chunk("TWO"),))
        async for _event in executor.execute(
            context=_runtime(), message="two", cancel_event=cancel
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
    caller = _caller()
    runtime = _runtime()
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
    from smart_rag_api.services.sse import chunks as chunk_mod

    real = chunk_mod.updates_mapping_from_chunk

    def _count(raw_chunk: object) -> dict[str, object] | None:
        """Count one parse then delegate.

        Args:
            raw_chunk: LangGraph updates payload.

        Returns:
            Normalized node mapping.
        """

        parses.append(raw_chunk)
        return real(raw_chunk)

    monkeypatch.setattr(
        "smart_rag_api.services.sse.executors.updates_mapping_from_chunk",
        _count,
    )
    stream = _RecordingAsyncStream((_verified_chunk("ONCE"),))
    executor = LangGraphQueryRunExecutor()
    _patch_recording_executor(monkeypatch, executor, _RecordingCompiled(stream))

    async def _drain() -> None:
        """Consume the patched executor."""

        async for _event in executor.execute(
            context=_runtime(),
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
    caller = _caller()
    runtime = _runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _probe() -> float:
        """Start a blocking append and tick the loop while it holds.

        Returns:
            Seconds the loop stayed able to sleep during the append.
        """

        append_task = asyncio.create_task(
            service._append_async(
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
    caller = _caller()
    runtime = _runtime()
    service.remember_admitted(caller, runtime, message="hello")
    with caplog.at_level(logging.INFO, logger="smart_rag_api.services.sse.service_persist"):
        persisted = service._append(
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
