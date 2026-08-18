"""Fail-closed tests for the 70% maintenance pause controller.

These tests inject telemetry fixtures. They do not busy-loop the host or
claim QT-CAP-001/002 from the 8-doc Packet 4 subset.
"""

from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.jobs.graph_index_service import GraphIndexService
from smart_rag_core.jobs.graph_writer import GraphWriterGuard
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.jobs.limits import (
    HYBRID_P95_PAUSE_GATE_MS,
    USER_LOAD_PAUSE_PERCENT,
)
from smart_rag_core.jobs.maintenance_pause import (
    PAUSE_REASON_CPU,
    PAUSE_REASON_IO,
    PAUSE_REASON_MEMORY,
    PAUSE_REASON_TELEMETRY_INVALID,
    PAUSE_REASON_TELEMETRY_MISSING,
    DatabasePressureSample,
    MaintenancePauseController,
    evaluate_maintenance_pause,
)
from smart_rag_core.release.packet4_load import (
    pressure_sample_from_docker_rows,
    rebuild_bm25_subset,
    reindex_hnsw,
)
from smart_rag_core.retrieval.lightrag_indexer import LightRagGraphIndexer
from smart_rag_core.schema.enums import JobErrorCategory


class _RecordingConnection:
    """Connection stub that records SQL and refuses unexpected work."""

    def __init__(self) -> None:
        """Start with an empty SQL log."""

        self.calls: list[str] = []
        self.autocommit = False

    def execute(self, sql: str) -> None:
        """Record one statement.

        Args:
            sql: Statement that would have run.

        Raises:
            AssertionError: If a caller runs SQL after a pause.
        """

        self.calls.append(sql)


def _below_threshold_sample() -> DatabasePressureSample:
    """Return a sample just under every pause gate.

    Returns:
        69.9% CPU/IO/memory and Hybrid p95 equal to QT-LAT-001.
    """

    return DatabasePressureSample(
        cpu_percent=69.9,
        io_percent=69.9,
        memory_percent=69.9,
        hybrid_p95_ms=HYBRID_P95_PAUSE_GATE_MS,
    )


def _index_service(
    *,
    pause_controller: MaintenancePauseController | None,
    isolated: list[object],
) -> GraphIndexService:
    """Build a GraphIndexService with rebuild stubs.

    Args:
        pause_controller: Injected controller, or None for fail-closed default.
        isolated: Appended when rebuild isolation would run.

    Returns:
        Service bound to connection and writer stubs.
    """

    def _verify_lock(**_kwargs: object) -> None:
        """Accept any lease-check kwargs without querying Postgres."""

        return None

    def _isolate() -> object:
        """Record that rebuild isolation would run.

        Returns:
            A new workspace id placeholder.
        """

        isolated.append("isolated")
        return uuid4()

    writer = SimpleNamespace(
        verify_lock_and_lease=_verify_lock,
        ensure_building_rebuild_workspace=_isolate,
    )
    return GraphIndexService(
        cast(psycopg.Connection, SimpleNamespace(commit=lambda: None)),
        indexer=cast(LightRagGraphIndexer, SimpleNamespace(adapter=object())),
        writer=cast(GraphWriterGuard, writer),
        repository=cast(LightragIndexJobRepository, SimpleNamespace()),
        pause_controller=pause_controller,
    )


def test_trigger_fires_at_exactly_seventy_percent() -> None:
    """CPU at 70% must pause fail-closed. 69.9% must not."""

    assert USER_LOAD_PAUSE_PERCENT == 70.0
    fired = evaluate_maintenance_pause(
        DatabasePressureSample(
            cpu_percent=70.0,
            io_percent=1.0,
            memory_percent=1.0,
            hybrid_p95_ms=100.0,
        )
    )
    assert fired.paused is True
    assert fired.trigger_70_percent_fired is True
    assert fired.fail_closed is False
    assert PAUSE_REASON_CPU in fired.reasons
    held = evaluate_maintenance_pause(_below_threshold_sample())
    assert held.paused is False
    assert held.trigger_70_percent_fired is False


def test_io_and_memory_seventy_percent_also_pause() -> None:
    """IO or memory at 70% pauses even when CPU is low."""

    io_fired = evaluate_maintenance_pause(
        DatabasePressureSample(
            cpu_percent=3.06,
            io_percent=70.0,
            memory_percent=10.0,
            hybrid_p95_ms=100.0,
        )
    )
    mem_fired = evaluate_maintenance_pause(
        DatabasePressureSample(
            cpu_percent=3.06,
            io_percent=10.0,
            memory_percent=70.0,
            hybrid_p95_ms=100.0,
        )
    )
    assert io_fired.paused is True
    assert PAUSE_REASON_IO in io_fired.reasons
    assert mem_fired.paused is True
    assert PAUSE_REASON_MEMORY in mem_fired.reasons


def test_missing_and_invalid_telemetry_fail_closed() -> None:
    """Unknown or NaN telemetry cannot be treated as below 70%."""

    missing = evaluate_maintenance_pause(None)
    assert missing.paused is True
    assert missing.fail_closed is True
    assert missing.trigger_70_percent_fired is False
    assert PAUSE_REASON_TELEMETRY_MISSING in missing.reasons
    empty = evaluate_maintenance_pause(DatabasePressureSample())
    assert empty.paused is True
    assert empty.fail_closed is True
    invalid = evaluate_maintenance_pause(
        DatabasePressureSample(cpu_percent=math.nan, io_percent=1.0)
    )
    assert invalid.paused is True
    assert invalid.fail_closed is True
    assert PAUSE_REASON_TELEMETRY_INVALID in invalid.reasons
    allowed = evaluate_maintenance_pause(
        DatabasePressureSample(),
        require_telemetry=False,
    )
    assert allowed.paused is False


def test_hybrid_p95_breach_pauses_below_cpu_threshold() -> None:
    """Hybrid p95 above QT-LAT-001 pauses even when CPU is 3.06%."""

    breach = evaluate_maintenance_pause(
        DatabasePressureSample(
            cpu_percent=3.06,
            io_percent=1.0,
            memory_percent=10.0,
            hybrid_p95_ms=HYBRID_P95_PAUSE_GATE_MS + 0.1,
        )
    )
    assert breach.paused is True
    assert breach.hybrid_p95_breach is True
    assert breach.trigger_70_percent_fired is False


def test_sampler_error_fail_closed() -> None:
    """A scraper exception must pause, not continue maintenance."""

    class _BrokenSampler:
        """Sampler that raises instead of returning telemetry."""

        def sample(self) -> DatabasePressureSample | None:
            """Raise as a failed scrape would.

            Returns:
                Never.

            Raises:
                RuntimeError: Always.
            """

            raise RuntimeError("scrape_failed")

    decision = MaintenancePauseController(_BrokenSampler()).decide()
    assert decision.paused is True
    assert decision.fail_closed is True
    assert decision.trigger_70_percent_fired is False


def test_hnsw_reindex_skips_sql_when_paused() -> None:
    """HNSW REINDEX must not run when the 70% trigger fires."""

    connection = _RecordingConnection()
    payload = reindex_hnsw(
        cast(psycopg.Connection, connection),
        pressure=DatabasePressureSample(
            cpu_percent=70.0,
            io_percent=1.0,
            memory_percent=1.0,
            hybrid_p95_ms=100.0,
        ),
    )
    assert payload["paused"] is True
    assert payload["reindex_executed"] is False
    assert payload["trigger_70_percent_fired"] is True
    assert payload["sample_is_eight_doc_subset"] is True
    assert connection.calls == []


def test_hnsw_reindex_missing_telemetry_skips_sql() -> None:
    """Missing pressure cannot proceed to REINDEX."""

    connection = _RecordingConnection()
    payload = reindex_hnsw(cast(psycopg.Connection, connection), pressure=None)
    assert payload["paused"] is True
    assert payload["fail_closed"] is True
    assert payload["reindex_executed"] is False
    assert connection.calls == []


def test_bm25_subset_skips_when_paused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BM25 subset rebuild must not open databases at 70% CPU."""

    def _boom(*_args: object, **_kwargs: object) -> object:
        """Fail if projection runs after a pause.

        Returns:
            Never.

        Raises:
            AssertionError: Always.
        """

        raise AssertionError("reproject must not run while paused")

    monkeypatch.setattr(
        "smart_rag_core.release.packet4_load.reproject_one_version",
        _boom,
    )
    payload = rebuild_bm25_subset(
        supabase_url="postgresql://unused",
        parade_url="postgresql://unused",
        triples=[("case", uuid4(), uuid4())],
        pressure=DatabasePressureSample(
            cpu_percent=70.0,
            io_percent=1.0,
            memory_percent=1.0,
            hybrid_p95_ms=100.0,
        ),
    )
    assert payload["paused"] is True
    assert payload["rebuild_executed"] is False
    assert payload["trigger_70_percent_fired"] is True


def test_lightrag_rebuild_pauses_at_seventy_percent() -> None:
    """Clean LightRAG rebuild must not isolate a workspace at 70% CPU."""

    isolated: list[object] = []
    lease_token = str(uuid4())
    service = _index_service(
        pause_controller=MaintenancePauseController.from_sample(
            DatabasePressureSample(
                cpu_percent=70.0,
                io_percent=1.0,
                memory_percent=1.0,
                hybrid_p95_ms=100.0,
            )
        ),
        isolated=isolated,
    )
    outcome = asyncio.run(
        service.process_claimed_job(
            {
                "id": str(uuid4()),
                "operation": "rebuild",
                "payload_ref": {"isolate_only": True},
            },
            job_lease_token=lease_token,
        )
    )
    assert isolated == []
    assert outcome.kind == "failed"
    assert outcome.error_category is JobErrorCategory.TRANSIENT
    assert outcome.last_error.startswith("maintenance_paused:")


def test_lightrag_rebuild_isolates_when_clear() -> None:
    """Below-threshold fixtures still isolate the rebuild workspace."""

    isolated: list[object] = []
    lease_token = str(uuid4())
    service = _index_service(
        pause_controller=MaintenancePauseController.from_sample(
            _below_threshold_sample()
        ),
        isolated=isolated,
    )
    outcome = asyncio.run(
        service.process_claimed_job(
            {
                "id": str(uuid4()),
                "operation": "rebuild",
                "payload_ref": {"isolate_only": True},
            },
            job_lease_token=lease_token,
        )
    )
    assert isolated == ["isolated"]
    assert outcome.kind == "completed"


def test_default_graph_rebuild_fail_closed_without_telemetry() -> None:
    """GraphIndexService defaults to fail-closed missing telemetry."""

    isolated: list[object] = []
    lease_token = str(uuid4())
    service = _index_service(pause_controller=None, isolated=isolated)
    outcome = asyncio.run(
        service.process_claimed_job(
            {
                "id": str(uuid4()),
                "operation": "rebuild",
                "payload_ref": {"isolate_only": True},
            },
            job_lease_token=lease_token,
        )
    )
    assert isolated == []
    assert outcome.kind == "failed"
    assert "telemetry_missing" in outcome.last_error


def test_docker_stats_fixture_does_not_claim_full_envelope() -> None:
    """Packet 4 docker scrape at 3.06% CPU must not fire 70% or 10k claims."""

    sample = pressure_sample_from_docker_rows(
        [{"Name": "supabase-db", "CPUPerc": "3.06%", "MemPerc": "12.0%"}]
    )
    assert sample is not None
    decision = evaluate_maintenance_pause(sample)
    assert decision.paused is False
    assert decision.trigger_70_percent_fired is False
    assert sample.cpu_percent == 3.06
