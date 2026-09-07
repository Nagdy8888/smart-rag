"""Contract tests for BM25 outbox reconcile claim, lease, and complete."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.jobs.bm25_repository import Bm25IndexJobRepository
from smart_rag_core.schema.enums import JobStatus

from tests.contract.integration_support import (
    packet8_paradedb_url,
    paradedb_reachable,
    require_supabase_db_url,
    resolve_supabase_db_url,
    try_connect,
)

pytestmark = pytest.mark.skipif(
    try_connect(resolve_supabase_db_url()) is None,
    reason="SUPABASE_DB_URL unset or Postgres unreachable",
)


def _repository(connection: psycopg.Connection, owner: str) -> Bm25IndexJobRepository:
    """Bind a worker BM25 repository."""

    return Bm25IndexJobRepository(connection, lease_owner=owner, lease_seconds=120)


def _insert_processing_job(
    connection: psycopg.Connection,
    *,
    lease_expires_at: datetime | None = None,
    lease_token: str | None = None,
    lease_owner: str | None = None,
) -> tuple[UUID, UUID]:
    """Insert one processing BM25 upsert with a synthetic version.

    Args:
        connection: Superuser-capable connection.
        lease_expires_at: Optional live or expired lease timestamp.
        lease_token: Optional lease token.
        lease_owner: Optional lease owner.

    Returns:
        ``(job_id, version_id)``.
    """

    document_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()
    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO app.documents (id, title) VALUES (%s, 'bm25-reconcile')",
            (document_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, status, chunk_set_hash
            )
            VALUES (%s, %s, 1, 'graph_ineligible', 'hash-reconcile')
            """,
            (version_id, document_id),
        )
        cursor.execute(
            """
            INSERT INTO app.bm25_index_jobs (
              id, version_id, operation, status, priority, idempotency_key,
              lease_expires_at, lease_token, lease_owner, created_at
            )
            VALUES (
              %s, %s, 'upsert'::app.bm25_job_operation,
              'processing'::app.job_status, 'critical'::app.job_priority,
              %s, %s, %s, %s, timestamptz '1970-01-01 00:00:00+00'
            )
            """,
            (
                job_id,
                version_id,
                f"bm25:reconcile:{job_id}",
                lease_expires_at,
                lease_token,
                lease_owner,
            ),
        )
    return job_id, version_id


def test_claim_reconcile_leases_unowned_processing_job() -> None:
    """Stuck processing rows with a null lease are claimable for reconcile."""

    owner = f"reconcile-owner-{uuid4()}"
    with psycopg.connect(require_supabase_db_url()) as connection:
        job_id, _version_id = _insert_processing_job(connection)
        connection.execute("SET ROLE app_worker")
        repo = _repository(connection, owner)
        claimed = None
        for _ in range(32):
            row = repo.claim_reconcile()
            if row is None:
                break
            if row["id"] == job_id:
                claimed = row
                break
        assert claimed is not None
        assert str(claimed["status"]) == JobStatus.PROCESSING.value
        assert claimed["lease_token"] is not None
        assert claimed["lease_owner"] == owner
        completed = repo.complete(claimed["id"], str(claimed["lease_token"]))
        again = repo.complete(claimed["id"], str(claimed["lease_token"]))
        second_claim = None
        for _ in range(32):
            row = repo.claim_reconcile()
            if row is None:
                break
            if row["id"] == job_id:
                second_claim = row
                break
        connection.rollback()
    assert str(completed["status"]) == JobStatus.COMPLETED.value
    assert str(again["status"]) == JobStatus.COMPLETED.value
    assert second_claim is None


def test_claim_reconcile_does_not_steal_live_lease() -> None:
    """Reconcile must not take a processing job with an unexpired lease."""

    owner = f"reconcile-live-{uuid4()}"
    future = datetime.now(tz=UTC) + timedelta(minutes=10)
    live_lease = f"live-{uuid4()}"
    with psycopg.connect(require_supabase_db_url()) as connection:
        job_id, _version_id = _insert_processing_job(
            connection,
            lease_expires_at=future,
            lease_token=live_lease,
            lease_owner="other-worker",
        )
        connection.execute("SET ROLE app_worker")
        claimed = _repository(connection, owner).claim_reconcile()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT lease_owner, lease_token
                FROM app.bm25_index_jobs
                WHERE id = %s
                """,
                (job_id,),
            )
            lease_row = cursor.fetchone()
        connection.rollback()
    assert claimed is None or claimed["id"] != job_id
    assert lease_row is not None
    assert lease_row[0] == "other-worker"
    assert lease_row[1] == live_lease


def test_app_api_cannot_claim_bm25_reconcile_job() -> None:
    """Reconcile claim is worker-role only; API role cannot execute it."""

    with psycopg.connect(require_supabase_db_url()) as connection:
        connection.execute("SET ROLE app_api")
        with connection.cursor() as cursor:
            cursor.execute("SAVEPOINT deny_reconcile")
            with pytest.raises(psycopg.Error):
                cursor.execute(
                    "SELECT app.claim_bm25_reconcile_job(%s, 120)",
                    ("api-owner",),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT deny_reconcile")
        connection.rollback()


@pytest.mark.skipif(
    packet8_paradedb_url() is None or not paradedb_reachable(),
    reason="local ParadeDB unavailable",
)
def test_reconcile_upsert_verify_fail_does_not_complete_outbox() -> None:
    """Live verify failure leaves Hybrid Ready untouched and fails the job."""

    from smart_rag_core.ingestion.bm25_projection import Bm25ProjectionService
    from smart_rag_core.schema.enums import JobErrorCategory

    parade_url = packet8_paradedb_url()
    assert parade_url is not None
    owner = f"reconcile-verify-{uuid4()}"
    with (
        psycopg.connect(require_supabase_db_url()) as supabase,
        psycopg.connect(parade_url, connect_timeout=8) as parade,
    ):
        job_id, version_id = _insert_processing_job(supabase)
        supabase.execute("SET ROLE app_worker")
        repo = _repository(supabase, owner)
        claimed = None
        for _ in range(32):
            row = repo.claim_reconcile()
            if row is None:
                break
            if row["id"] == job_id:
                claimed = row
                break
        assert claimed is not None
        parade.execute("SET ROLE paradedb_writer")
        service = Bm25ProjectionService(supabase, parade)
        decision = service.reconcile_upsert_job(version_id=version_id, job_id=job_id)
        assert decision.action == "fail"
        repo.fail(
            job_id,
            str(claimed["lease_token"]),
            error_category=JobErrorCategory.TRANSIENT,
            last_error=decision.reason,
        )
        with supabase.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM app.bm25_index_jobs WHERE id = %s",
                (job_id,),
            )
            status_row = cursor.fetchone()
            cursor.execute(
                """
                SELECT dv.status, d.current_version_id
                FROM app.document_versions AS dv
                JOIN app.documents AS d ON d.id = dv.document_id
                WHERE dv.id = %s
                """,
                (version_id,),
            )
            version_row = cursor.fetchone()
        supabase.rollback()
    assert status_row is not None
    assert str(status_row[0]) in {JobStatus.PENDING.value, JobStatus.DEAD_LETTER.value}
    assert version_row is not None
    assert version_row[0] == "graph_ineligible"
    assert version_row[1] is None
