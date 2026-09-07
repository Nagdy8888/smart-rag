"""Contract tests for idempotent hybrid_index chaining."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
import pytest
from langchain_core.runnables import RunnableConfig
from smart_rag_agents.ingestion.crawl_graph import (
    IngestionCrawlState,
    execute_approved_crawl,
)
from smart_rag_agents.ingestion.scan_graph import IngestionScanState, promote_object
from smart_rag_core.ingestion.crawl.adapter import (
    CrawlRunResult,
    WebSnapshotRecord,
)
from smart_rag_core.jobs.hybrid_enqueue import (
    enqueue_hybrid_index_job,
    hybrid_index_idempotency_key,
)
from smart_rag_core.schema.enums import JobStatus

from tests.contract.integration_support import (
    read_process_env,
    require_supabase_db_url,
    try_connect,
)
from tests.contract.test_upload_finalize import (
    insert_auth_user,
    read_authorization_version,
)


def _require_postgres() -> psycopg.Connection:
    """Open Postgres or skip unless the job integration gate is required."""

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Hybrid index enqueue requires reachable Supabase Postgres")
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    return connection


@pytest.fixture
def worker_connection() -> Iterator[psycopg.Connection]:
    """Yield a connection truncated to an empty job queue."""

    connection = _require_postgres()
    connection.execute("SET ROLE postgres")
    connection.execute(
        """
        TRUNCATE
          app.job_operation_ledger,
          app.budget_reservations,
          app.ingestion_jobs
        RESTART IDENTITY CASCADE
        """
    )
    connection.commit()
    yield connection
    connection.rollback()
    connection.close()


def test_duplicate_hybrid_index_enqueue_is_one_job(
    worker_connection: psycopg.Connection,
) -> None:
    """Scan/crawl completion replay must not create a second hybrid_index row."""

    document_id = uuid4()
    version_id = uuid4()
    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, created_by)
            VALUES (%s, 'hybrid-index-enqueue', NULL)
            """,
            (document_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (id, document_id, version_number, status)
            VALUES (%s, %s, 1, 'parsing')
            """,
            (version_id, document_id),
        )
    worker_connection.execute("SET ROLE app_worker")
    worker_connection.commit()
    payload = {
        "storage_bucket": "documents-originals",
        "storage_path": f"{document_id}/{version_id}/file.txt",
        "content_hash": "a" * 64,
        "content_class": "synthetic",
        "graph_eligible": False,
    }
    first = enqueue_hybrid_index_job(
        worker_connection,
        document_id=document_id,
        version_id=version_id,
        payload_ref=payload,
        estimated_size_bytes=12,
        estimated_cost_usd=Decimal("0.05"),
    )
    worker_connection.commit()
    second = enqueue_hybrid_index_job(
        worker_connection,
        document_id=document_id,
        version_id=version_id,
        payload_ref=payload,
        estimated_size_bytes=12,
        estimated_cost_usd=Decimal("0.05"),
    )
    worker_connection.commit()
    assert first.id == second.id
    assert first.idempotency_key == hybrid_index_idempotency_key(version_id)
    assert first.job_kind == "hybrid_index"
    assert first.status is JobStatus.PENDING
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM app.ingestion_jobs
            WHERE version_id = %s AND job_kind = 'hybrid_index'
            """,
            (version_id,),
        )
        row = cursor.fetchone()
    assert row is not None
    assert int(row[0]) == 1


def test_promote_object_enqueues_hybrid_index_after_scan(
    worker_connection: psycopg.Connection,
) -> None:
    """Successful promotion enqueues one ``hybrid_index`` job for the version."""

    document_id = uuid4()
    version_id = uuid4()
    postgres_url = require_supabase_db_url()
    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO app.documents (id, title) VALUES (%s, 'scan-promote-hybrid')",
            (document_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, status, graph_eligible
            )
            VALUES (%s, %s, 1, 'scanning', false)
            """,
            (version_id, document_id),
        )
    worker_connection.commit()
    state: IngestionScanState = {
        "job_id": str(uuid4()),
        "lease_token": "unused",
        "document_id": str(document_id),
        "version_id": str(version_id),
        "operation_key": f"scan:{version_id}",
        "storage_bucket": "documents-quarantine",
        "storage_path": f"{document_id}/{version_id}/file.txt",
        "content_hash": "a" * 64,
        "byte_size": 12,
        "media_type": "text/plain",
        "destination_bucket": "documents-originals",
        "destination_path": f"{document_id}/{version_id}/file.txt",
        "reservation_id": None,
        "declared_category": "synthetic",
        "attestation_policy_version": "phase3_v1",
        "uploader_user_id": None,
        "review_approved": True,
        "content_class": "synthetic",
        "crash_after": None,
        "status": "scanning",
        "scan_result": "clean",
        "detail": "",
    }
    config = cast(
        RunnableConfig,
        {
            "configurable": {
                "postgres_url": postgres_url,
                "storage_url": "http://127.0.0.1:54321",
                "storage_admin_secret": "test-storage-secret",
            }
        },
    )
    with patch("smart_rag_agents.ingestion.scan_graph.PromotionSaga") as saga_cls:
        saga_cls.return_value.run.return_value = None
        result = promote_object(state, config)
    assert result["status"] == "promoted"
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM app.ingestion_jobs
            WHERE version_id = %s AND job_kind = 'hybrid_index'
            """,
            (version_id,),
        )
        row = cursor.fetchone()
    assert row is not None
    assert int(row[0]) == 1


def test_crawl_complete_enqueues_hybrid_index(
    worker_connection: psycopg.Connection,
) -> None:
    """Successful crawl completion enqueues one ``hybrid_index`` with crawl refs."""

    owner_id = uuid4()
    postgres_url = require_supabase_db_url()
    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        insert_auth_user(cursor, owner_id, f"{owner_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'owner', true, true)
            """,
            (owner_id,),
        )
        auth_version = read_authorization_version(cursor)
    worker_connection.commit()
    worker_connection.execute("SET ROLE app_api")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT document_id, version_id, source_id, job_id
            FROM app.enqueue_approved_website_crawl(
              %s, 'owner', %s,
              'https://example.test/docs',
              'example.test',
              'Example docs',
              %s,
              1, 5, 'synthetic', false, 'phase3_v1'
            )
            """,
            (owner_id, auth_version, f"crawl-enqueue:{uuid4()}"),
        )
        row = cursor.fetchone()
    worker_connection.commit()
    assert row is not None
    _document_id, version_id, source_id, _job_id = row
    snapshot = WebSnapshotRecord(
        snapshot_id=uuid4(),
        canonical_url="https://example.test/docs",
        title="Example",
        content_type="text/html",
        content_hash="b" * 64,
        storage_bucket="web-snapshots",
        storage_path=f"{source_id}/page.html",
        wire_bytes=24,
        decoded_bytes=24,
        redirect_chain=("https://example.test/docs",),
        peer_ip="203.0.113.10",
        pinned_ips=("203.0.113.10",),
    )

    def _fake_crawl(
        _self: object,
        scope: object,
        *,
        source_id: UUID,
        crawl_version: int,
    ) -> CrawlRunResult:
        """Return one in-memory snapshot without contacting the live proxy."""

        _ = source_id
        return CrawlRunResult(
            crawl_version=crawl_version,
            policy_version=getattr(scope, "policy_version", "crawl_v1"),
            start_url=getattr(scope, "start_url", "https://example.test/docs"),
            pages_fetched=1,
            wire_bytes_total=24,
            decoded_bytes_total=24,
            snapshots=[snapshot],
            fetch_events=[],
            failure_reason=None,
        )

    state: IngestionCrawlState = {
        "job_id": str(_job_id),
        "lease_token": "unused",
        "source_id": str(source_id),
        "version_id": str(version_id),
        "operation_key": f"crawl:{version_id}",
        "content_class": "synthetic",
        "graph_eligible": False,
        "attestation_policy_version": "phase3_v1",
        "status": "crawl_pending",
        "pages_fetched": 0,
        "crawl_run_id": None,
        "detail": "",
    }
    config = cast(
        RunnableConfig,
        {
            "configurable": {
                "postgres_url": postgres_url,
                "crawl_proxy_url": "http://127.0.0.1:18080",
                "storage_url": "http://127.0.0.1:54321",
                "storage_admin_secret": "test-storage-secret",
            }
        },
    )
    with (
        patch(
            "smart_rag_agents.ingestion.crawl_graph.BoundedCrawlAdapter.crawl",
            _fake_crawl,
        ),
        patch(
            "smart_rag_agents.ingestion.crawl_graph.scan_crawl_snapshots_before_index",
            return_value=None,
        ),
    ):
        result = execute_approved_crawl(state, config)
    assert result["status"] == "crawl_completed"
    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT payload_ref
            FROM app.ingestion_jobs
            WHERE version_id = %s AND job_kind = 'hybrid_index'
            """,
            (version_id,),
        )
        hybrid = cursor.fetchone()
    assert hybrid is not None
    payload = hybrid[0]
    assert payload["crawl_run_id"]
    assert payload["snapshots"]


def test_crawl_dirty_scan_does_not_enqueue_hybrid_index(
    worker_connection: psycopg.Connection,
) -> None:
    """Missing/dirty snapshot scan fails the crawl job without hybrid_index."""

    owner_id = uuid4()
    postgres_url = require_supabase_db_url()
    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        insert_auth_user(cursor, owner_id, f"{owner_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'owner', true, true)
            """,
            (owner_id,),
        )
        auth_version = read_authorization_version(cursor)
    worker_connection.commit()
    worker_connection.execute("SET ROLE app_api")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT document_id, version_id, source_id, job_id
            FROM app.enqueue_approved_website_crawl(
              %s, 'owner', %s,
              'https://example.test/docs',
              'example.test',
              'Example docs',
              %s,
              1, 5, 'synthetic', true, 'phase3_v1'
            )
            """,
            (owner_id, auth_version, f"crawl-enqueue-dirty:{uuid4()}"),
        )
        row = cursor.fetchone()
    worker_connection.commit()
    assert row is not None
    _document_id, version_id, source_id, _job_id = row
    snapshot = WebSnapshotRecord(
        snapshot_id=uuid4(),
        canonical_url="https://example.test/docs",
        title="Example",
        content_type="text/html",
        content_hash="c" * 64,
        storage_bucket="web-snapshots",
        storage_path=f"{source_id}/page.html",
        wire_bytes=24,
        decoded_bytes=24,
        redirect_chain=("https://example.test/docs",),
        peer_ip="203.0.113.10",
        pinned_ips=("203.0.113.10",),
    )

    def _fake_crawl(
        _self: object,
        scope: object,
        *,
        source_id: UUID,
        crawl_version: int,
    ) -> CrawlRunResult:
        """Return one in-memory snapshot without contacting the live proxy."""

        _ = source_id
        return CrawlRunResult(
            crawl_version=crawl_version,
            policy_version=getattr(scope, "policy_version", "crawl_v1"),
            start_url=getattr(scope, "start_url", "https://example.test/docs"),
            pages_fetched=1,
            wire_bytes_total=24,
            decoded_bytes_total=24,
            snapshots=[snapshot],
            fetch_events=[],
            failure_reason=None,
        )

    state: IngestionCrawlState = {
        "job_id": str(_job_id),
        "lease_token": "unused",
        "source_id": str(source_id),
        "version_id": str(version_id),
        "operation_key": f"crawl:{version_id}",
        "content_class": "synthetic",
        "graph_eligible": True,
        "attestation_policy_version": "phase3_v1",
        "status": "crawl_pending",
        "pages_fetched": 0,
        "crawl_run_id": None,
        "detail": "",
    }
    config = cast(
        RunnableConfig,
        {
            "configurable": {
                "postgres_url": postgres_url,
                "crawl_proxy_url": "http://127.0.0.1:18080",
                "storage_url": "http://127.0.0.1:54321",
                "storage_admin_secret": "test-storage-secret",
            }
        },
    )
    with (
        patch(
            "smart_rag_agents.ingestion.crawl_graph.BoundedCrawlAdapter.crawl",
            _fake_crawl,
        ),
        patch(
            "smart_rag_agents.ingestion.crawl_graph.scan_crawl_snapshots_before_index",
            return_value="snapshot_scan_infected:Eicar-Test-Signature",
        ),
    ):
        result = execute_approved_crawl(state, config)
    assert result["status"] == "crawl_failed"
    assert "snapshot_scan_infected" in str(result["detail"])
    worker_connection.execute("SET ROLE postgres")
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM app.ingestion_jobs
            WHERE version_id = %s AND job_kind = 'hybrid_index'
            """,
            (version_id,),
        )
        hybrid = cursor.fetchone()
    assert hybrid is not None
    assert int(hybrid[0]) == 0
