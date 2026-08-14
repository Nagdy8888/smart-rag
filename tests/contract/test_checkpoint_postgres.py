"""Contract tests for pinned Postgres checkpointer and interrupt/resume."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from langgraph.checkpoint.postgres.base import MIGRATIONS
from smart_rag_agents.ingestion.checkpointer import (
    EXPECTED_CHECKPOINT_VERSIONS,
    open_ingestion_checkpointer,
)
from smart_rag_agents.ingestion.graph import build_probe_ingestion_graph
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.jobs.ledger import JobOperationLedger

from tests.contract.integration_support import (
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINTER_MODULE = (
    REPO_ROOT
    / "apps"
    / "agents"
    / "src"
    / "smart_rag_agents"
    / "ingestion"
    / "checkpointer.py"
)


def _require_postgres() -> psycopg.Connection:
    """Open Postgres or skip unless the job integration gate is required."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Checkpointer integration requires reachable Supabase Postgres")
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    return connection


@pytest.fixture
def postgres_url() -> Iterator[str]:
    """Yield the local database URL or skip when unreachable."""

    connection = _require_postgres()
    connection.close()
    yield resolve_supabase_db_url()


def test_langgraph_checkpoint_postgres_pin_matches_library() -> None:
    """Pinned 3.1.2 must match langgraph-checkpoint 4.x used by langgraph 1.2.11."""

    assert version("langgraph-checkpoint-postgres") == "3.1.2"
    assert version("langgraph") == "1.2.11"
    assert EXPECTED_CHECKPOINT_VERSIONS == tuple(range(len(MIGRATIONS)))
    assert len(MIGRATIONS) == 10


def test_checkpointer_factory_never_calls_setup() -> None:
    """Runtime wiring must not auto-migrate; Phase 2/3 SQL owns DDL."""

    source = CHECKPOINTER_MODULE.read_text(encoding="utf-8")
    assert "saver.setup(" not in source
    assert ".setup()" not in source.replace("PostgresSaver.setup()", "")


def test_checkpoint_schema_versions_match_pinned_library(postgres_url: str) -> None:
    """Migrated ``langgraph.checkpoint_migrations`` must include versions 0-9."""

    checkpointer = open_ingestion_checkpointer(postgres_url, max_size=1)
    try:
        with checkpointer.pool.connection() as connection:
            rows = connection.execute(
                "SELECT v FROM checkpoint_migrations ORDER BY v"
            ).fetchall()
        versions = [int(row["v"]) for row in rows]
        assert versions == list(EXPECTED_CHECKPOINT_VERSIONS)
        with checkpointer.pool.connection() as connection:
            exists = connection.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'langgraph'
                  AND table_name = 'checkpoint_writes'
                  AND column_name = 'task_path'
                """
            ).fetchone()
        assert exists is not None
    finally:
        checkpointer.close()


def test_probe_interrupt_resume_does_not_duplicate_ledger(
    postgres_url: str,
) -> None:
    """Checkpoint interrupt then resume writes one ledger row for the probe."""

    worker = psycopg.connect(postgres_url)
    worker.execute("SET ROLE postgres")
    worker.execute(
        """
        TRUNCATE
          app.job_operation_ledger,
          app.budget_reservations,
          app.ingestion_jobs
        RESTART IDENTITY CASCADE
        """
    )
    worker.execute("SET ROLE app_worker")
    worker.commit()
    repo = IngestionJobRepository(
        worker,
        lease_owner="checkpoint-resume-owner",
        lease_seconds=120,
    )
    job = repo.enqueue(
        idempotency_key=f"checkpoint-resume:{uuid4()}",
        job_kind="probe",
        payload_ref={"operation_key": "checkpoint_probe"},
        estimated_size_bytes=1,
        estimated_cost_usd=Decimal("0.01"),
    )
    worker.commit()
    claimed = repo.claim()
    worker.commit()
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.lease_token is not None

    checkpointer = open_ingestion_checkpointer(postgres_url, max_size=1)
    try:
        interrupted = build_probe_ingestion_graph(
            checkpointer=checkpointer.saver,
            interrupt_after=["validate_lease"],
        )
        resumed = build_probe_ingestion_graph(checkpointer=checkpointer.saver)
        config = {
            "configurable": {
                "thread_id": str(claimed.id),
                "postgres_url": postgres_url,
                "lease_owner": "checkpoint-resume-owner",
                "job_lease_seconds": 120,
            }
        }
        graph_input = {
            "job_id": str(claimed.id),
            "lease_token": claimed.lease_token,
            "document_id": None,
            "version_id": None,
            "operation_key": "checkpoint_probe",
            "storage_bucket": None,
            "storage_path": None,
            "status": "probe_pending",
            "ledger_written": False,
            "detail": "",
        }
        interrupted.invoke(graph_input, config)  # pyright: ignore[reportUnknownMemberType]
        snapshot = interrupted.get_state(config)  # pyright: ignore[reportUnknownMemberType]
        assert snapshot.next == ("boundary_probe",)
        with worker.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM app.job_operation_ledger
                WHERE job_id = %s
                """,
                (claimed.id,),
            )
            row = cursor.fetchone()
        assert row is not None
        assert int(row[0]) == 0

        result = resumed.invoke(None, config)  # pyright: ignore[reportUnknownMemberType]
        assert result["status"] == "probe_validated"
        assert result["ledger_written"] is True

        replayed = resumed.invoke(graph_input, config)  # pyright: ignore[reportUnknownMemberType]
        assert replayed["ledger_written"] is True
        with worker.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM app.job_operation_ledger
                WHERE job_id = %s AND operation_key = %s
                """,
                (claimed.id, "checkpoint_probe"),
            )
            row = cursor.fetchone()
        assert row is not None
        assert int(row[0]) == 1
        ledger = JobOperationLedger(worker)
        fetched = ledger.fetch_result(
            job_table="ingestion_jobs",
            job_id=claimed.id,
            operation_key="checkpoint_probe",
        )
        assert fetched is not None
        assert fetched.get("probe") == "phase3_packet2"
    finally:
        checkpointer.close()
        worker.close()
