"""Ordered background writer for one run's SSE executor drafts."""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID, uuid4

import pytest
from smart_rag_api.services.sse.event_writer import (
    RunEventWriter,
    executor_draft_writer,
)
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.store import PersistedRunEvent

from tests.support.query_sse import caller as make_caller

WRITER_LOGGER = "smart_rag_api.services.sse.event_writer"


class _Recorder:
    """Append stand-in that records drafts and can delay, block, or fail."""

    def __init__(
        self,
        *,
        delays: tuple[float, ...] = (),
        fail_at: int | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        """Configure the fake append.

        Args:
            delays: Sleep in seconds per call, by call index (missing is 0).
            fail_at: Zero-based call index that raises ``RuntimeError``.
            gate: When set, every call waits for this event first.
        """

        self.delays = delays
        self.fail_at = fail_at
        self.gate = gate
        self.calls = 0
        self.persisted: list[tuple[str, dict[str, object]]] = []

    async def __call__(
        self, event_type: str, payload: dict[str, object]
    ) -> PersistedRunEvent | None:
        """Record one draft after the configured wait.

        Args:
            event_type: Catalog event type.
            payload: Draft payload.

        Returns:
            Always None; the writer ignores the row.

        Raises:
            RuntimeError: On the configured failing call.
        """

        index = self.calls
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        if index < len(self.delays):
            await asyncio.sleep(self.delays[index])
        if index == self.fail_at:
            raise RuntimeError("append failed")
        self.persisted.append((event_type, payload))
        return None


def _draft(index: int) -> tuple[str, dict[str, object]]:
    """Return one numbered status draft.

    Args:
        index: Draft number.

    Returns:
        ``status`` draft whose stage names the number.
    """

    return ("status", {"stage": f"stage_{index}", "status": "running"})


def test_writer_preserves_submit_order() -> None:
    """Fifty drafts with uneven append delays persist in submit order."""

    recorder = _Recorder(delays=tuple(((i * 7) % 5) / 1000.0 for i in range(50)))

    async def _run() -> None:
        """Submit fifty drafts, then close."""

        writer = RunEventWriter(recorder, run_id=uuid4())
        for index in range(50):
            await writer.submit(*_draft(index))
        await writer.close()

    asyncio.run(_run())
    assert recorder.persisted == [_draft(index) for index in range(50)]


def test_submit_does_not_wait_for_append() -> None:
    """Five submits return long before their 100 ms appends finish."""

    recorder = _Recorder(delays=(0.1,) * 5)

    async def _run() -> float:
        """Time five submits, then flush and close.

        Returns:
            Seconds spent in the five ``submit`` calls.
        """

        writer = RunEventWriter(recorder, run_id=uuid4())
        started = time.monotonic()
        for index in range(5):
            await writer.submit(*_draft(index))
        elapsed = time.monotonic() - started
        await writer.flush()
        await writer.close()
        return elapsed

    assert asyncio.run(_run()) < 0.05
    assert len(recorder.persisted) == 5


def test_submit_waits_when_queue_full() -> None:
    """With ``max_pending=2`` a fourth submit waits behind a blocked append."""

    async def _run() -> tuple[bool, list[tuple[str, dict[str, object]]]]:
        """Fill the queue behind a blocked append, then release it.

        Returns:
            Whether the fourth submit timed out, and the persisted drafts.
        """

        gate = asyncio.Event()
        recorder = _Recorder(gate=gate)
        writer = RunEventWriter(recorder, run_id=uuid4(), max_pending=2)
        for index in range(3):
            await writer.submit(*_draft(index))
        try:
            await asyncio.wait_for(writer.submit(*_draft(3)), timeout=0.1)
        except TimeoutError:
            timed_out = True
        else:
            timed_out = False
        gate.set()
        await writer.close()
        return timed_out, recorder.persisted

    timed_out, persisted = asyncio.run(_run())
    assert timed_out is True
    assert persisted == [_draft(index) for index in range(3)]


def test_flush_waits_for_all_submitted() -> None:
    """``flush`` returns only after every submitted draft is persisted."""

    recorder = _Recorder(delays=(0.02,) * 5)

    async def _run() -> int:
        """Submit five slow drafts and flush.

        Returns:
            Persisted count right after ``flush`` returns.
        """

        writer = RunEventWriter(recorder, run_id=uuid4())
        for index in range(5):
            await writer.submit(*_draft(index))
        await writer.flush()
        count = len(recorder.persisted)
        await writer.close()
        return count

    assert asyncio.run(_run()) == 5


def test_append_exception_stops_writer_and_reraises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing append stops later writes; flush and submit re-raise it."""

    recorder = _Recorder(fail_at=1)

    async def _run() -> None:
        """Submit three drafts where the second fails."""

        writer = RunEventWriter(recorder, run_id=uuid4())
        for index in range(3):
            await writer.submit(*_draft(index))
        with pytest.raises(RuntimeError, match="append failed"):
            await writer.flush()
        with pytest.raises(RuntimeError, match="append failed"):
            await writer.submit(*_draft(3))
        await writer.close()

    with caplog.at_level(logging.INFO, logger=WRITER_LOGGER):
        asyncio.run(_run())
    assert recorder.persisted == [_draft(0)]
    assert recorder.calls == 2
    stopped = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "sse.writer_stopped"
    ]
    assert len(stopped) == 1
    assert "skipped=1" in stopped[0].getMessage()
    assert getattr(stopped[0], "error_type", None) == "RuntimeError"


def test_close_is_idempotent_and_abort_after_close_is_noop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two closes log one summary; abort after close does nothing."""

    recorder = _Recorder()

    async def _run() -> None:
        """Close twice, abort, and prove submit is refused after close."""

        writer = RunEventWriter(recorder, run_id=uuid4())
        await writer.submit(*_draft(0))
        await writer.close()
        await writer.close()
        writer.abort()
        with pytest.raises(RuntimeError, match="closed"):
            await writer.submit(*_draft(1))

    with caplog.at_level(logging.INFO, logger=WRITER_LOGGER):
        asyncio.run(_run())
    summaries = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "sse.writer_summary"
    ]
    assert len(summaries) == 1
    assert "events=1" in summaries[0].getMessage()
    assert recorder.persisted == [_draft(0)]


def test_writer_rejects_empty_queue_bound() -> None:
    """``max_pending`` below one is a configuration error."""

    with pytest.raises(ValueError, match="max_pending"):
        RunEventWriter(_Recorder(), run_id=uuid4(), max_pending=0)


def test_executor_writer_skips_non_terminal_drafts_after_cancel() -> None:
    """After cancel, status drafts are skipped and terminals still persist."""

    calls: list[str] = []

    async def _append(
        caller: CallerContext,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> PersistedRunEvent | None:
        """Record the event type only.

        Args:
            caller: Run owner.
            run_id: Run id.
            event_type: Catalog event type.
            payload: Draft payload.

        Returns:
            Always None.
        """

        del caller, run_id, payload
        calls.append(event_type)
        return None

    async def _run() -> None:
        """Persist one status, cancel, then submit a status and a terminal."""

        cancel = asyncio.Event()
        writer = executor_draft_writer(
            _append, caller=make_caller(), run_id=uuid4(), cancel_event=cancel
        )
        await writer.submit(*_draft(0))
        await writer.flush()
        cancel.set()
        await writer.submit(*_draft(1))
        await writer.submit("cancelled", {})
        await writer.close()

    asyncio.run(_run())
    assert calls == ["status", "cancelled"]
