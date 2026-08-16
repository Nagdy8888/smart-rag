"""Contract tests for leased ingestion jobs and SKIP LOCKED claiming."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from decimal import Decimal

import psycopg
import pytest
from smart_rag_core.jobs.dead_letter import DeadLetterService
from smart_rag_core.jobs.exceptions import JobAdmissionError, JobLeaseError
from smart_rag_core.jobs.ingestion_repository import IngestionJobRepository
from smart_rag_core.jobs.ledger import JobOperationLedger
from smart_rag_core.jobs.lightrag_repository import LightragIndexJobRepository
from smart_rag_core.jobs.limits import (
    GRAPH_HANDOFF_PAUSE_PENDING_INDEX,
    MAX_PENDING_INGESTION_JOBS,
)
from smart_rag_core.schema.enums import (
    JobErrorCategory,
    JobPriority,
    LightragJobOperation,
)

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
            pytest.fail("Job lease integration requires reachable Supabase Postgres")
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    connection.execute("SET ROLE app_worker")
    return connection


@pytest.fixture(autouse=True)
def isolate_job_tables(worker_connection: psycopg.Connection) -> Iterator[None]:
    """Truncate queue tables so contract tests start from an empty durable state."""

    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            TRUNCATE
              app.job_operation_ledger,
              app.budget_reservations,
              app.ingestion_jobs,
              app.dead_letter_jobs,
              app.lightrag_index_jobs
            RESTART IDENTITY CASCADE
            """
        )
    worker_connection.execute("SET ROLE app_worker")
    worker_connection.commit()
    yield
    worker_connection.rollback()


@pytest.fixture
def worker_connection() -> Iterator[psycopg.Connection]:
    """Yield one ``app_worker`` connection rolled back after each test."""

    connection = _require_postgres()
    yield connection
    connection.rollback()
    connection.close()


def _repository(connection: psycopg.Connection, owner: str) -> IngestionJobRepository:
    """Build one ingestion job repository bound to ``owner``.

    Args:
        connection: Open ``app_worker`` connection.
        owner: Lease owner identifier.

    Returns:
        Repository using a 120-second lease.
    """

    return IngestionJobRepository(connection, lease_owner=owner, lease_seconds=120)


def test_duplicate_enqueue_returns_same_job(
    worker_connection: psycopg.Connection,
) -> None:
    """Duplicate idempotency keys return one logical job row."""

    repo = _repository(worker_connection, "unit-test-owner")
    key = f"dup:{uuid.uuid4()}"
    first = repo.enqueue(
        idempotency_key=key,
        job_kind="probe",
        estimated_size_bytes=10,
        estimated_cost_usd=Decimal("0.01"),
        payload_ref={"operation_key": "probe"},
    )
    worker_connection.commit()
    second = repo.enqueue(
        idempotency_key=key,
        job_kind="probe",
        estimated_size_bytes=10,
        estimated_cost_usd=Decimal("0.01"),
        payload_ref={"operation_key": "probe"},
    )
    worker_connection.commit()
    assert first.id == second.id


def test_invalid_lease_token_denies_ledger_write(
    worker_connection: psycopg.Connection,
) -> None:
    """Ledger writes reject invalid lease tokens."""

    repo = _repository(worker_connection, "lease-deny-owner")
    job = repo.enqueue(
        idempotency_key=f"lease-deny:{uuid.uuid4()}",
        job_kind="probe",
        estimated_size_bytes=1,
        estimated_cost_usd=Decimal("0.01"),
        payload_ref={"operation_key": "probe"},
    )
    worker_connection.commit()
    ledger = JobOperationLedger(worker_connection)
    invalid_lease_token = "invalid-token-fixture"  # noqa: S105
    with pytest.raises(JobLeaseError):
        ledger.record_completed(
            job_table="ingestion_jobs",
            job_id=job.id,
            operation_key="probe",
            lease_token=invalid_lease_token,
        )


def test_skip_locked_claim_is_exclusive(worker_connection: psycopg.Connection) -> None:
    """Two workers cannot concurrently hold the same valid lease."""

    job_key = f"skip-locked:{uuid.uuid4()}"
    repo = _repository(worker_connection, "seed-owner")
    repo.enqueue(
        idempotency_key=job_key,
        job_kind="probe",
        priority=JobPriority.HIGH,
        estimated_size_bytes=1,
        estimated_cost_usd=Decimal("0.01"),
        payload_ref={"operation_key": "probe"},
    )
    worker_connection.commit()

    barrier = threading.Barrier(2)
    claims: list[str | None] = []
    lock = threading.Lock()
    url = resolve_supabase_db_url()

    def claim(owner: str) -> None:
        """Claim one job from a dedicated connection as ``owner``.

        Args:
            owner: Lease owner used for the claim RPC.
        """

        assert url is not None
        with psycopg.connect(url) as connection:
            connection.execute("SET ROLE app_worker")
            repository = IngestionJobRepository(
                connection,
                lease_owner=owner,
                lease_seconds=120,
            )
            barrier.wait(timeout=5)
            claimed = repository.claim()
            connection.commit()
            with lock:
                claims.append(claimed.lease_token if claimed else None)

    threads = [
        threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    tokens = [token for token in claims if token is not None]
    assert len(tokens) == 1


def test_heartbeat_renews_and_cancel_blocks_writes(
    worker_connection: psycopg.Connection,
) -> None:
    """Heartbeat succeeds for valid leases; cancellation blocks ledger writes."""

    repo = _repository(worker_connection, "heartbeat-owner")
    repo.enqueue(
        idempotency_key=f"heartbeat:{uuid.uuid4()}",
        job_kind="probe",
        estimated_size_bytes=1,
        estimated_cost_usd=Decimal("0.01"),
        payload_ref={"operation_key": "probe"},
    )
    worker_connection.commit()
    claimed = repo.claim()
    assert claimed is not None and claimed.lease_token is not None
    worker_connection.commit()
    repo.heartbeat(claimed.id, claimed.lease_token)
    worker_connection.commit()
    repo.cancel(claimed.id, claimed.lease_token)
    worker_connection.commit()
    ledger = JobOperationLedger(worker_connection)
    with pytest.raises(JobLeaseError):
        ledger.record_completed(
            job_table="ingestion_jobs",
            job_id=claimed.id,
            operation_key="probe",
            lease_token=claimed.lease_token,
        )


def test_dead_letter_replay_creates_traceable_attempt(
    worker_connection: psycopg.Connection,
) -> None:
    """Replay inserts a new pending job linked to dead-letter evidence."""

    repo = _repository(worker_connection, "dl-replay-owner")
    job = repo.enqueue(
        idempotency_key=f"dl:{uuid.uuid4()}",
        job_kind="probe",
        estimated_size_bytes=1,
        estimated_cost_usd=Decimal("0.01"),
        payload_ref={"operation_key": "probe"},
    )
    worker_connection.commit()
    claimed = repo.claim()
    assert claimed is not None and claimed.lease_token is not None
    worker_connection.commit()
    dead = repo.fail(
        claimed.id,
        claimed.lease_token,
        error_category=JobErrorCategory.PERMANENT,
        last_error="forced",
        move_to_dead_letter=True,
    )
    worker_connection.commit()
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM app.dead_letter_jobs
            WHERE source_job_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (job.id,),
        )
        row = cursor.fetchone()
        assert row is not None
        dead_letter_id = row[0]
    replay = DeadLetterService(worker_connection).replay_ingestion(dead_letter_id)
    worker_connection.commit()
    assert replay.id != dead.id
    assert replay.payload_ref.get("replay_of_dead_letter_id") == str(dead_letter_id)


def test_pending_cap_is_observable(worker_connection: psycopg.Connection) -> None:
    """Admission exposes pending-cap backpressure at the configured limit."""

    repo = _repository(worker_connection, "cap-owner")
    for index in range(MAX_PENDING_INGESTION_JOBS):
        repo.enqueue(
            idempotency_key=f"cap:{uuid.uuid4()}:{index}",
            job_kind="probe",
            estimated_size_bytes=1,
            estimated_cost_usd=Decimal("0.01"),
        )
    worker_connection.commit()
    with pytest.raises(JobAdmissionError) as caught:
        repo.enqueue(
            idempotency_key=f"cap:{uuid.uuid4()}:overflow",
            job_kind="probe",
            estimated_size_bytes=1,
            estimated_cost_usd=Decimal("0.01"),
        )
    assert caught.value.reason == "pending_cap"


def test_graph_handoff_pause_blocks_index_claims(
    worker_connection: psycopg.Connection,
) -> None:
    """Pending index handoffs above 50 pause new index claims but not remove."""

    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, created_by)
            VALUES (%s, 'graph-handoff-pause', NULL)
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
    worker_connection.execute("SET ROLE app_worker")
    lightrag_repo = LightragIndexJobRepository(
        worker_connection,
        lease_owner="graph-pause-owner",
        lease_seconds=120,
    )
    for index in range(GRAPH_HANDOFF_PAUSE_PENDING_INDEX + 1):
        lightrag_repo.enqueue_index_handoff(
            idempotency_key=f"graph-index:{uuid.uuid4()}:{index}",
            document_id=document_id,
            version_id=version_id,
        )
    worker_connection.commit()
    assert lightrag_repo.graph_handoff_paused() is True
    claimed_index = lightrag_repo.claim()
    worker_connection.commit()
    assert claimed_index is None
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.lightrag_index_jobs (
              document_id,
              version_id,
              operation,
              idempotency_key,
              priority
            )
            VALUES (%s, %s, %s, %s, 'high')
            """,
            (
                document_id,
                version_id,
                LightragJobOperation.REMOVE.value,
                f"graph-remove:{uuid.uuid4()}",
            ),
        )
    worker_connection.commit()
    claimed_remove = lightrag_repo.claim()
    worker_connection.commit()
    assert claimed_remove is not None
    assert claimed_remove["operation"] == LightragJobOperation.REMOVE.value
