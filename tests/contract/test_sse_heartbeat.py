"""Contract tests for 15s SSE heartbeats and five held streams."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from smart_rag_api.services.sse_stream import FixtureQueryRunExecutor
from smart_rag_core.runtime.offload import sample_event_loop_lag
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.sse.catalog import HEARTBEAT_INTERVAL_SECONDS
from smart_rag_core.sse.store import MemoryRunEventStore

from tests.contract.sse_http_support import (
    OWNER_ID,
    RecordingAdmitService,
    client_headers,
    lifespanless_sse_app,
    patch_sse_rate_limits,
    require_str,
    sse_headers,
)
from tests.unit.typed_openapi import json_object, permit_test_identity

_HELD_STREAMS = 5
_WAIT_SECONDS = 16.0
_HEARTBEAT_JITTER_SECONDS = 2.0
_P95_LAG_SECONDS = 0.050


def test_production_heartbeat_interval_constant() -> None:
    """CI asserts the production interval even if a fixture clock is used elsewhere."""

    assert HEARTBEAT_INTERVAL_SECONDS == 15


def _owner_caller() -> CallerContext:
    """Return the in-memory SSE test owner.

    Returns:
        Caller matching ``OWNER_ID``.
    """

    return CallerContext(
        user_id=OWNER_ID,
        role=UserRole.OWNER,
        authorization_version=1,
    )


def test_five_held_streams_meet_lag_and_heartbeat_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Five concurrent fixture SSE connections hold ≥16s with real 15s heartbeats.

    ``httpx.ASGITransport`` delivers the EventSource body when the generator
    completes, so cadence is measured from persisted ``heartbeat`` rows (the
    same append path the socket uses). No OpenAI. Live Composite LLM proof
    remains packet 8.
    """

    permit_test_identity(monkeypatch)
    patch_sse_rate_limits(monkeypatch)
    store = MemoryRunEventStore()
    executor = FixtureQueryRunExecutor(hold_seconds=30, emit_completed=False)
    admit = RecordingAdmitService()
    application = lifespanless_sse_app(store=store, executor=executor, admit=admit)
    caller = _owner_caller()

    async def _hold_one(client: httpx.AsyncClient, run_id: str) -> None:
        """Keep one EventSource connection open until cancelled.

        Args:
            client: Shared ASGI client.
            run_id: Admitted run.
        """

        async with client.stream(
            "GET",
            f"/runs/{run_id}/events",
            headers=sse_headers(),
        ) as response:
            assert response.status_code == 200
            assert response.headers.get("content-type", "").startswith(
                "text/event-stream"
            )
            assert response.headers.get("x-accel-buffering") == "no"
            async for _chunk in response.aiter_text():
                await asyncio.sleep(0)

    async def _wait_persisted_heartbeat(
        run_id: UUID, started: float
    ) -> tuple[float, int]:
        """Wait until the store has a heartbeat for ``run_id``.

        Args:
            run_id: Admitted run.
            started: Loop clock when streams were attached.

        Returns:
            Seconds until the first persisted heartbeat and heartbeat count.
        """

        loop = asyncio.get_running_loop()
        while True:
            events = store.list_after(caller, run_id=run_id, after=0)
            beats = [item for item in events if item.event_type == "heartbeat"]
            if beats:
                return loop.time() - started, len(beats)
            if loop.time() - started > 20:
                return loop.time() - started, len(beats)
            await asyncio.sleep(0.05)

    async def _run() -> None:
        """Admit five runs, hold streams, and sample event-loop lag."""

        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            run_ids: list[str] = []
            for _ in range(_HELD_STREAMS):
                submitted = await client.post(
                    f"/conversations/{uuid4()}/messages",
                    json={"message": "hold", "idempotency_key": str(uuid4())},
                    headers=client_headers(),
                )
                assert submitted.status_code == 202
                run_ids.append(require_str(json_object(submitted.json())["run_id"]))

            async def _lag() -> float:
                """Sample lag while the five streams are open.

                Returns:
                    Maximum p95 lag observed across windows.
                """

                worst = 0.0
                deadline = asyncio.get_running_loop().time() + _WAIT_SECONDS
                while asyncio.get_running_loop().time() < deadline:
                    sample = await sample_event_loop_lag(
                        samples=10, interval_seconds=0.01
                    )
                    worst = max(worst, sample.p95_seconds)
                return worst

            started = asyncio.get_running_loop().time()
            stream_tasks = [
                asyncio.create_task(_hold_one(client, run_id)) for run_id in run_ids
            ]
            lag_task = asyncio.create_task(_lag())
            holds = await asyncio.gather(
                *[
                    _wait_persisted_heartbeat(UUID(run_id), started)
                    for run_id in run_ids
                ]
            )
            lag = await lag_task
            for task in stream_tasks:
                task.cancel()
            await asyncio.gather(*stream_tasks, return_exceptions=True)

        elapsed_list = [item[0] for item in holds]
        beat_counts = [item[1] for item in holds]
        assert all(count >= 1 for count in beat_counts), beat_counts
        for elapsed in elapsed_list:
            assert elapsed >= HEARTBEAT_INTERVAL_SECONDS - _HEARTBEAT_JITTER_SECONDS
            jitter = abs(elapsed - HEARTBEAT_INTERVAL_SECONDS)
            assert jitter < _HEARTBEAT_JITTER_SECONDS, elapsed
        assert lag < _P95_LAG_SECONDS, lag
        assert executor.start_count == _HELD_STREAMS

    asyncio.run(_run())
