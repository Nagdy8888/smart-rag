"""Contract tests for Packet 3 graph writer lease, lock, and budget isolation."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.jobs.admission import JobAdmissionService
from smart_rag_core.jobs.exceptions import (
    GraphWriterLostError,
    JobAdmissionError,
    JobLeaseError,
)
from smart_rag_core.jobs.graph_metrics import GraphMetricsService
from smart_rag_core.jobs.graph_writer import GraphWriterGuard, graph_advisory_lock_keys
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.jobs.limits import (
    DEFAULT_DAILY_GRAPH_INDEX_BUDGET_USD,
    DEFAULT_DAILY_INGESTION_BUDGET_USD,
    DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD,
)
from smart_rag_core.schema.enums import GraphWorkspaceState, JobErrorCategory

from tests.contract.integration_support import (
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)


def _require_postgres() -> psycopg.Connection:
    """Open Postgres or fail closed when integration gate requires it."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Graph writer integration requires reachable Supabase Postgres")
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    connection.execute("SET ROLE app_worker")
    return connection


@pytest.fixture
def worker_connection() -> Iterator[psycopg.Connection]:
    """Yield one ``app_worker`` connection rolled back after each test."""

    connection = _require_postgres()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def isolate_graph_writer(worker_connection: psycopg.Connection) -> Iterator[None]:
    """Reset writer lease, jobs, and budget rows without dropping workspaces.

    Truncates every ``app.budget_reservations`` kind, including leftover
    ``ingestion_daily`` spend on a dirty shared local database. Graph kind
    isolation must not depend on that leftover daily total.
    """

    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.graph_writer_lease
            SET owner = NULL, token = NULL, expires_at = NULL
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        cursor.execute(
            """
            UPDATE app.graph_workspaces
            SET state = 'building'::app.graph_workspace_state
            WHERE workspace_key = 'company_default'
            """
        )
        cursor.execute(
            """
            UPDATE app.company_settings
            SET
              daily_ingestion_budget_usd = %s,
              daily_graph_index_budget_usd = %s,
              monthly_graph_maintenance_budget_usd = %s
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """,
            (
                DEFAULT_DAILY_INGESTION_BUDGET_USD,
                DEFAULT_DAILY_GRAPH_INDEX_BUDGET_USD,
                DEFAULT_MONTHLY_GRAPH_MAINTENANCE_BUDGET_USD,
            ),
        )
        cursor.execute(
            """
            TRUNCATE app.budget_reservations, app.lightrag_index_jobs
            RESTART IDENTITY CASCADE
            """
        )
    worker_connection.execute("SET ROLE app_worker")
    worker_connection.commit()
    yield
    worker_connection.rollback()


def test_two_workers_cannot_occupy_writer_lease(
    worker_connection: psycopg.Connection,
) -> None:
    """The durable writer lease admits only one owner at a time."""

    first = GraphWriterGuard(
        worker_connection,
        lease_owner="writer-a",
        lease_seconds=120,
    )
    job_id, token = _claim_dummy_job(worker_connection, owner="writer-a")
    first.occupy(job_id=job_id, job_lease_token=token)
    worker_connection.commit()

    url = resolve_supabase_db_url()
    second_conn = psycopg.connect(url)
    try:
        second_conn.execute("SET ROLE app_worker")
        second = GraphWriterGuard(
            second_conn,
            lease_owner="writer-b",
            lease_seconds=120,
        )
        job_b, token_b = _claim_dummy_job(second_conn, owner="writer-b")
        with pytest.raises(GraphWriterLostError, match="writer_lease_occupied"):
            second.occupy(job_id=job_b, job_lease_token=token_b)
        second_conn.rollback()
    finally:
        second_conn.close()


def test_advisory_lock_excludes_second_session(
    worker_connection: psycopg.Connection,
) -> None:
    """Session advisory lock, not the vendor schema lock, serializes writers."""

    url = resolve_supabase_db_url()
    keys = graph_advisory_lock_keys("company_default")
    first = psycopg.connect(url)
    second = psycopg.connect(url)
    try:
        first.autocommit = True
        second.autocommit = True
        first.execute("SET ROLE app_worker")
        second.execute("SET ROLE app_worker")
        with first.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", keys)
            held = cursor.fetchone()
        assert held is not None and held[0] is True
        with second.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", keys)
            busy = cursor.fetchone()
        assert busy is not None and busy[0] is False
        with first.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s, %s)", keys)
    finally:
        first.close()
        second.close()
    del worker_connection


def test_lease_loss_quarantines_workspace(
    worker_connection: psycopg.Connection,
) -> None:
    """Expired writer lease plus quarantine RPC leaves the workspace quarantined."""

    job_id, token = _claim_dummy_job(worker_connection, owner="writer-expire")
    guard = GraphWriterGuard(
        worker_connection,
        lease_owner="writer-expire",
        lease_seconds=120,
    )
    guard.occupy(job_id=job_id, job_lease_token=token)
    worker_connection.commit()
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.graph_writer_lease
            SET expires_at = timezone('utc', now()) - interval '1 hour'
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        cursor.execute(
            "SELECT app.validate_active_graph_writer_lease(%s, %s)",
            ("writer-expire", guard.writer_token),
        )
        still_valid = cursor.fetchone()
    assert still_valid is not None and still_valid[0] is False
    guard.quarantine(reason="writer_lease_lost", source_job_id=job_id)
    worker_connection.commit()
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT state
            FROM app.graph_workspaces
            WHERE workspace_key = 'company_default'
            """
        )
        row = cursor.fetchone()
    assert row is not None
    assert str(row[0]) == GraphWorkspaceState.QUARANTINED.value


def test_graph_budget_kinds_are_isolated(
    worker_connection: psycopg.Connection,
) -> None:
    """Graph index spend must not consume ingestion_daily or maintenance.

    Seeds committed ``ingestion_daily`` spend at the company cap first so a
    dirty shared local database cannot make this assertion depend on leftover
    Hybrid ingest totals. Graph kinds must still admit; Hybrid ingest must
    remain exhausted; ``ingestion_daily`` is not a valid graph kind.
    """

    _seed_committed_budget(
        worker_connection,
        reservation_kind="ingestion_daily",
        amount_usd=Decimal(str(DEFAULT_DAILY_INGESTION_BUDGET_USD)),
    )
    worker_connection.commit()
    admission = JobAdmissionService(worker_connection)
    graph_index = admission.create_graph_budget_reservation(
        reservation_kind="graph_index",
        estimated_cost_usd=Decimal("0.50"),
    )
    maintenance = admission.create_graph_budget_reservation(
        reservation_kind="graph_maintenance",
        estimated_cost_usd=Decimal("0.10"),
    )
    worker_connection.commit()
    assert graph_index != maintenance
    with pytest.raises(JobAdmissionError) as invalid_kind:
        admission.create_graph_budget_reservation(
            reservation_kind="ingestion_daily",
            estimated_cost_usd=Decimal("0.01"),
        )
    assert invalid_kind.value.reason == "invalid_graph_reservation_kind"
    with pytest.raises(JobAdmissionError) as ingestion_exhausted:
        admission.create_ingestion_budget_reservation(
            estimated_cost_usd=Decimal("0.01"),
        )
    assert ingestion_exhausted.value.reason == "budget_exhausted"


def test_metrics_insufficient_sample_until_maps(
    worker_connection: psycopg.Connection,
) -> None:
    """ETA stays insufficient-sample while mapping-verified count is zero."""

    metrics = GraphMetricsService(worker_connection).collect()
    assert metrics.mapping_verified_count == 0
    assert metrics.eta_confidence == "insufficient-sample"
    assert metrics.documents_per_hour is None
    assert metrics.bulk_window_active is False


def test_lightrag_heartbeat_complete_fail_rpcs(
    worker_connection: psycopg.Connection,
) -> None:
    """Heartbeat/complete/fail RPCs honor the claimed lease token."""

    repo = LightragIndexJobRepository(
        worker_connection,
        lease_owner="pkt3-rpc-owner",
        lease_seconds=120,
    )
    job_id, token = _claim_dummy_job(worker_connection, owner="pkt3-rpc-owner")
    repo.heartbeat(job_id, token)
    worker_connection.commit()
    completed = repo.complete(
        job_id,
        token,
        result={"vendor_status": "processed", "maps_verified": False},
    )
    worker_connection.commit()
    assert str(completed["status"]) == "completed"
    assert completed["payload_ref"].get("maps_verified") is False

    job_id_fail, token_fail = _claim_dummy_job(
        worker_connection,
        owner="pkt3-rpc-owner",
        suffix="fail",
    )
    failed = repo.fail(
        job_id_fail,
        token_fail,
        error_category=JobErrorCategory.TRANSIENT,
        last_error="forced_fail",
    )
    worker_connection.commit()
    assert str(failed["status"]) in {"pending", "dead_letter"}
    with pytest.raises(JobLeaseError):
        repo.heartbeat(job_id_fail, token_fail)


def test_runtime_role_still_denied_ddl(
    worker_connection: psycopg.Connection,
) -> None:
    """Packet 3 must not restore DDL rights on the runtime LightRAG role."""

    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        cursor.execute("SET ROLE app_lightrag")
        cursor.execute("SAVEPOINT denied_ddl")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "CREATE TABLE lightrag.pkt3_forbidden_ddl (id integer PRIMARY KEY)"
            )
        cursor.execute("ROLLBACK TO SAVEPOINT denied_ddl")
        cursor.execute("RELEASE SAVEPOINT denied_ddl")
        cursor.execute("RESET ROLE")
    worker_connection.execute("SET ROLE app_worker")


def _seed_committed_budget(
    connection: psycopg.Connection,
    *,
    reservation_kind: str,
    amount_usd: Decimal,
) -> None:
    """Insert one committed reservation so leftover spend is explicit.

    Args:
        connection: Open connection; role switches to ``postgres`` for insert.
        reservation_kind: Durable budget kind such as ``ingestion_daily``.
        amount_usd: Positive committed amount in USD.

    Side Effects:
        Inserts one ``app.budget_reservations`` row and restores ``app_worker``.
        Postgres remains the spend authority; Valkey is not consulted.
    """

    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.budget_reservations (
              reservation_kind,
              amount_usd,
              status,
              expires_at,
              committed_at
            )
            VALUES (
              %s,
              %s,
              'committed'::app.budget_reservation_status,
              timezone('utc', now()) + interval '2 hours',
              timezone('utc', now())
            )
            """,
            (reservation_kind, amount_usd),
        )
    connection.execute("SET ROLE app_worker")


def _claim_dummy_job(
    connection: psycopg.Connection,
    *,
    owner: str,
    suffix: str = "ok",
) -> tuple[object, str]:
    """Insert and claim one LightRAG job for lease RPC tests.

    Args:
        connection: ``app_worker`` connection.
        owner: Lease owner.
        suffix: Idempotency suffix.

    Returns:
        Job id and lease token.
    """

    document_id = uuid4()
    version_id = uuid4()
    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, created_by)
            VALUES (%s, 'pkt3-writer', NULL)
            """,
            (document_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (id, document_id, version_number)
            VALUES (%s, %s, 1)
            """,
            (version_id, document_id),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s, graph_eligible = true
            WHERE id = %s
            """,
            (version_id, document_id),
        )
    connection.execute("SET ROLE app_worker")
    repo = LightragIndexJobRepository(
        connection,
        lease_owner=owner,
        lease_seconds=120,
    )
    repo.enqueue_index_handoff(
        idempotency_key=f"pkt3-{owner}-{suffix}-{uuid4()}",
        document_id=document_id,
        version_id=version_id,
    )
    connection.commit()
    claimed = repo.claim()
    connection.commit()
    assert claimed is not None
    return claimed["id"], str(claimed["lease_token"])
