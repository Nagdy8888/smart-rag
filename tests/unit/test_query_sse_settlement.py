"""SSE reservation settlement, fallthrough terminals, and facade exports."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from smart_rag_api.services.query_sse_mapping import QuerySseMapper
from smart_rag_api.services.sse_stream import (
    FixtureQueryRunExecutor,
    QueryRunRegistry,
    SseStreamService,
)
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.sse.store import MemoryRunEventStore

from tests.support.query_sse import (
    _caller,
    _runtime,
)


def test_sse_service_settles_reservation_once_on_terminal(monkeypatch: Any) -> None:
    """Terminal persist true-ups the reservation exactly once."""

    calls: list[UUID] = []

    class _Conn:
        """No-op connection used by settlement."""

        def execute(self, statement: str) -> None:
            """Ignore SET ROLE.

            Args:
                statement: SQL.
            """

            del statement

        def commit(self) -> None:
            """No-op commit."""

            return None

        def __enter__(self) -> _Conn:
            """Enter the dummy connection context.

            Returns:
                This connection.
            """

            return self

        def __exit__(self, *args: object) -> None:
            """Ignore context-exit arguments.

            Args:
                *args: Exception context unused by the stub.
            """

            del args

    def _connect(url: str) -> _Conn:
        """Return the no-op connection.

        Args:
            url: DSN.

        Returns:
            Dummy connection.
        """

        del url
        return _Conn()

    def _true_up(
        connection: object, *, caller: CallerContext, reservation_id: UUID
    ) -> None:
        """Record settlement.

        Args:
            connection: Unused.
            caller: Owner.
            reservation_id: Reservation.
        """

        del connection, caller
        calls.append(reservation_id)

    monkeypatch.setattr(
        "smart_rag_api.services.sse.run_settlement.psycopg.connect",
        _connect,
    )
    monkeypatch.setattr(
        "smart_rag_api.services.sse.run_settlement.true_up_query_reservation",
        _true_up,
    )
    store = MemoryRunEventStore()
    registry = QueryRunRegistry()
    executor = FixtureQueryRunExecutor()
    service = SseStreamService(
        store=store,
        registry=registry,
        executor=executor,
        sse_schema_version="1",
        postgres_url="postgresql://example",
    )
    caller = _caller()
    runtime = _runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _drain() -> list[str]:
        """Collect SSE frames from the stream service.

        Returns:
            Raw SSE frame strings.
        """

        frames: list[str] = []
        async for frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            frames.append(frame)
        return frames

    frames = asyncio.run(_drain())
    assert any(
        "event: completed" in frame or "event: error" in frame for frame in frames
    )
    assert calls == [runtime.reservation_id]
    service._append(caller, runtime.run_id, "error", {"code": "run_failed"})
    assert calls == [runtime.reservation_id]


def test_sse_service_fallthrough_without_terminal_is_error_not_completed() -> None:
    """If the executor yields no terminal, persist error rather than completed."""

    store = MemoryRunEventStore()
    registry = QueryRunRegistry()
    executor = FixtureQueryRunExecutor(emit_completed=False)
    service = SseStreamService(
        store=store,
        registry=registry,
        executor=executor,
        sse_schema_version="1",
    )
    caller = _caller()
    runtime = _runtime()
    service.remember_admitted(caller, runtime, message="hello")

    async def _drain() -> list[str]:
        """Collect SSE frames from the stream service.

        Returns:
            Raw SSE frame strings.
        """

        frames: list[str] = []
        async for frame in service.iter_frames(
            caller, run_id=runtime.run_id, after=0, context=runtime
        ):
            frames.append(frame)
        return frames

    frames = asyncio.run(_drain())
    joined = "".join(frames)
    assert "event: completed" not in joined
    assert "event: error" in joined
    assert "run_failed" in joined


def test_mapper_type_is_exported_for_executor() -> None:
    """Executor persist path depends on QuerySseMapper.verified_text."""

    mapper = QuerySseMapper()
    assert mapper.verified_text == ""


def test_sse_facade_reexports_public_types() -> None:
    """Documented ``sse_stream`` imports stay identical to the package."""

    from smart_rag_api.services import sse
    from smart_rag_api.services.sse_stream import (
        FixtureQueryRunExecutor as FacadeFixture,
    )
    from smart_rag_api.services.sse_stream import (
        SseStreamService as FacadeService,
    )

    assert FacadeService is sse.SseStreamService
    assert FacadeFixture is sse.FixtureQueryRunExecutor
