"""File and website paths to BM25 outbox and verified Hybrid Ready."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.ingestion.parser.website import merge_website_parse_results

from tests.contract.hybrid_ready_driver import (
    drive_hybrid_ready,
    parse_local_bytes,
    persist_parse_to_bm25_outbox,
)
from tests.contract.integration_support import (
    packet8_paradedb_url,
    paradedb_host_reachable,
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)
from tests.fixtures.parser import build_html_fixture, build_pdf_text_fixture


def _require_postgres() -> psycopg.Connection:
    """Open Postgres or fail when the job integration gate is required."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Hybrid Ready E2E requires reachable Supabase Postgres")
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    return connection


@pytest.fixture
def worker_connection() -> Iterator[psycopg.Connection]:
    """Yield a worker-capable connection."""

    connection = _require_postgres()
    yield connection
    connection.rollback()
    connection.close()


def test_synthetic_file_reaches_bm25_outbox_without_hand_insert(
    worker_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Parse a synthetic PDF through canonical persist; BM25 outbox is created."""

    _ = tmp_path
    payload, _digest = build_pdf_text_fixture()
    parsed = parse_local_bytes(payload, filename="policy.pdf", format_key="pdf")
    _document_id, version_id, bm25_job_id = persist_parse_to_bm25_outbox(
        worker_connection,
        parse_result=parsed,
        title="synthetic-file",
        filename="policy.pdf",
    )
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT operation, status
            FROM app.bm25_index_jobs
            WHERE id = %s AND version_id = %s
            """,
            (bm25_job_id, version_id),
        )
        row = cursor.fetchone()
    assert row is not None
    assert row[0] == "upsert"
    assert str(row[1]) == "pending"


def test_synthetic_website_reaches_bm25_outbox_without_hand_insert(
    worker_connection: psycopg.Connection,
) -> None:
    """Merged website snapshots persist as one version with one BM25 job."""

    first_payload, _first_hash = build_html_fixture()
    second = (
        b"<html><body><main><p>Second page body.</p></main></body></html>"
    )
    first = parse_local_bytes(first_payload, filename="p1.html", format_key="html")
    page_two = parse_local_bytes(second, filename="p2.html", format_key="html")
    combined = "c" * 64
    merged = merge_website_parse_results((first, page_two), combined_hash=combined)
    _document_id, version_id, bm25_job_id = persist_parse_to_bm25_outbox(
        worker_connection,
        parse_result=merged,
        title="synthetic-website",
        filename="website.html",
    )
    with worker_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM app.bm25_index_jobs
            WHERE id = %s AND version_id = %s AND operation = 'upsert'
            """,
            (bm25_job_id, version_id),
        )
        row = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM app.document_chunks WHERE version_id = %s",
            (version_id,),
        )
        chunks = cursor.fetchone()
    assert row is not None
    assert int(row[0]) == 1
    assert chunks is not None
    assert int(chunks[0]) >= 1


def test_synthetic_file_reaches_verified_hybrid_ready() -> None:
    """File fixture reaches Hybrid Ready after BM25 verify on local ParadeDB."""

    parade_url = packet8_paradedb_url()
    if parade_url is None or not paradedb_host_reachable():
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Hybrid Ready E2E requires Packet 8 ParadeDB overlay")
        pytest.skip("ParadeDB host overlay not reachable")
    payload, _digest = build_pdf_text_fixture()
    parsed = parse_local_bytes(payload, filename="policy.pdf", format_key="pdf")
    result = drive_hybrid_ready(
        supabase_url=resolve_supabase_db_url(),
        parade_url=parade_url,
        parse_result=parsed,
        title=f"hybrid-file-{uuid4()}",
        filename="policy.pdf",
    )
    assert result.hybrid_ready is True
    assert result.status in {"hybrid_ready", "graph_ineligible"}
    assert result.bm25_job_id is not None


def test_synthetic_website_reaches_verified_hybrid_ready() -> None:
    """Website merge reaches Hybrid Ready after BM25 verify on local ParadeDB."""

    parade_url = packet8_paradedb_url()
    if parade_url is None or not paradedb_host_reachable():
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Website Hybrid Ready E2E requires Packet 8 ParadeDB overlay")
        pytest.skip("ParadeDB host overlay not reachable")
    payload, digest = build_html_fixture()
    parsed = parse_local_bytes(payload, filename="site.html", format_key="html")
    merged = merge_website_parse_results((parsed,), combined_hash=digest)
    result = drive_hybrid_ready(
        supabase_url=resolve_supabase_db_url(),
        parade_url=parade_url,
        parse_result=merged,
        title=f"hybrid-site-{uuid4()}",
        filename="website.html",
    )
    assert result.hybrid_ready is True
    assert result.status in {"hybrid_ready", "graph_ineligible"}
