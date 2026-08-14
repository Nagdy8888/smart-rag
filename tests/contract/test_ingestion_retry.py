"""Contract tests for role-scoped ingestion retry and dead-letter replay."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from smart_rag_api.main import create_app
from smart_rag_core.jobs.dead_letter import DeadLetterService
from smart_rag_core.jobs.exceptions import JobRetryNotAllowedError
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.schema.enums import JobErrorCategory, JobStatus

from tests.contract.integration_support import (
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)


def _require_postgres() -> psycopg.Connection:
    """Open Postgres or skip unless the job integration gate is required."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Retry integration requires reachable Supabase Postgres")
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    return connection


@pytest.fixture
def worker_connection() -> Iterator[psycopg.Connection]:
    """Yield a connection that can SET ROLE between postgres, worker, and api."""

    connection = _require_postgres()
    connection.execute("SET ROLE postgres")
    connection.execute(
        """
        TRUNCATE
          app.job_operation_ledger,
          app.budget_reservations,
          app.ingestion_jobs,
          app.dead_letter_jobs
        RESTART IDENTITY CASCADE
        """
    )
    connection.commit()
    yield connection
    connection.rollback()
    connection.close()


def _repository(connection: psycopg.Connection, owner: str) -> IngestionJobRepository:
    return IngestionJobRepository(connection, lease_owner=owner, lease_seconds=120)


def test_dead_letter_retry_creates_second_job_and_retains_original(
    worker_connection: psycopg.Connection,
) -> None:
    """API retry of a dead-letter job inserts a new pending row."""

    worker_connection.execute("SET ROLE app_worker")
    repo = _repository(worker_connection, "retry-dl-owner")
    job = repo.enqueue(
        idempotency_key=f"retry-dl:{uuid4()}",
        job_kind="probe",
        estimated_size_bytes=1,
        estimated_cost_usd=Decimal("0.01"),
    )
    worker_connection.commit()
    claimed = repo.claim()
    worker_connection.commit()
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.lease_token is not None
    dead = repo.fail(
        claimed.id,
        claimed.lease_token,
        error_category=JobErrorCategory.PERMANENT,
        last_error="forced-terminal",
        move_to_dead_letter=True,
    )
    worker_connection.commit()
    assert dead.status is JobStatus.DEAD_LETTER
    original_error = dead.last_error
    original_attempts = dead.attempt_count

    worker_connection.execute("SET ROLE app_api")
    replay = DeadLetterService(worker_connection).retry_ingestion(dead.id)
    worker_connection.commit()
    assert replay.detail == "dead_letter_replayed"
    assert replay.job.id != dead.id
    assert replay.original_job_id == dead.id
    assert replay.job.status is JobStatus.PENDING
    assert replay.job.payload_ref.get("replay_of_source_job_id") == str(dead.id)
    assert "replay_of_dead_letter_id" in replay.job.payload_ref

    worker_connection.execute("SET ROLE app_worker")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            "SELECT status, last_error, attempt_count FROM app.ingestion_jobs WHERE id = %s",
            (dead.id,),
        )
        source = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM app.dead_letter_jobs WHERE source_job_id = %s",
            (dead.id,),
        )
        dl_count = cursor.fetchone()
    assert source is not None
    assert str(source[0]) == "dead_letter"
    assert source[1] == original_error
    assert int(source[2]) == original_attempts
    assert dl_count is not None
    assert int(dl_count[0]) == 1


def test_backoff_retry_clears_next_attempt_without_wiping_error(
    worker_connection: psycopg.Connection,
) -> None:
    """Failed-but-not-DL retry only clears ``next_attempt_at``."""

    worker_connection.execute("SET ROLE app_worker")
    repo = _repository(worker_connection, "retry-backoff-owner")
    job = repo.enqueue(
        idempotency_key=f"retry-backoff:{uuid4()}",
        job_kind="probe",
        estimated_size_bytes=1,
        estimated_cost_usd=Decimal("0.01"),
    )
    worker_connection.commit()
    claimed = repo.claim()
    worker_connection.commit()
    assert claimed is not None
    assert claimed.lease_token is not None
    failed = repo.fail(
        claimed.id,
        claimed.lease_token,
        error_category=JobErrorCategory.TRANSIENT,
        last_error="transient-timeout",
    )
    worker_connection.commit()
    assert failed.status is JobStatus.PENDING
    assert failed.next_attempt_at is not None
    assert failed.last_error == "transient-timeout"
    attempt_count = failed.attempt_count

    worker_connection.execute("SET ROLE app_api")
    retried = DeadLetterService(worker_connection).retry_ingestion(job.id)
    worker_connection.commit()
    assert retried.detail == "backoff_cleared"
    assert retried.job.id == job.id
    assert retried.job.next_attempt_at is None
    assert retried.job.last_error == "transient-timeout"
    assert retried.job.attempt_count == attempt_count


def test_completed_job_retry_is_rejected(
    worker_connection: psycopg.Connection,
) -> None:
    """Completed jobs cannot be retried."""

    worker_connection.execute("SET ROLE app_worker")
    repo = _repository(worker_connection, "retry-complete-owner")
    job = repo.enqueue(
        idempotency_key=f"retry-complete:{uuid4()}",
        job_kind="probe",
        estimated_size_bytes=1,
        estimated_cost_usd=Decimal("0.01"),
    )
    worker_connection.commit()
    claimed = repo.claim()
    worker_connection.commit()
    assert claimed is not None
    assert claimed.lease_token is not None
    repo.complete(claimed.id, claimed.lease_token)
    worker_connection.commit()

    worker_connection.execute("SET ROLE app_api")
    with pytest.raises(JobRetryNotAllowedError):
        DeadLetterService(worker_connection).retry_ingestion(job.id)
    worker_connection.rollback()


def test_member_retry_route_remains_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """Members cannot invoke the retry HTTP action."""

    monkeypatch.setenv("APP_ENV", "test")
    with TestClient(create_app()) as client:
        response = client.post(
            "/ingestion/jobs/00000000-0000-4000-8000-000000000001/retry",
            headers={
                "X-Test-User-Id": "00000000-0000-4000-8000-000000000002",
                "X-Test-Role": "member",
                "X-Test-Authorization-Version": "1",
            },
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden"
