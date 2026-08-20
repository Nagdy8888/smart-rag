"""Contract tests for Packet 4 map expansion, replay, and Graph Ready."""

from __future__ import annotations

# GraphMappingService must load before chunking.normalize to avoid a
# settings/jobs/retrieval import cycle. Keep this order.
# ruff: noqa: I001

import asyncio
from collections.abc import Callable, Iterator
from typing import Protocol, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.jobs.graph_mapping_service import (
    GraphMappingService,
    GraphVendorReader,
)
from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.jobs.graph_writer import GraphWriterGuard
from smart_rag_core.retrieval.graph import (
    bind_graph_source_text,
    canonical_passage_source_id,
)

from tests.contract.integration_support import (
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
    typed_module_attr,
)
import tests.unit.test_graph_mapping as graph_mapping_unit


class _FakeVendorFactory(Protocol):
    """Constructor for the in-memory vendor catalog used by mapping contracts."""

    def __call__(
        self,
        *,
        status: str = "processed",
        file_path: str | None = None,
        chunks: list[dict[str, object]] | None = None,
        nodes: list[dict[str, object]] | None = None,
        edges: list[dict[str, object]] | None = None,
    ) -> GraphVendorReader:
        """Build one vendor-reader stub."""

        ...


_FakeVendor = typed_module_attr(
    graph_mapping_unit,
    "_FakeVendor",
    cast(_FakeVendorFactory, None),
)
_StubWriter = typed_module_attr(
    graph_mapping_unit,
    "_StubWriter",
    cast("Callable[[], GraphWriterGuard]", None),
)


def _require_postgres() -> psycopg.Connection:
    """Open Postgres or skip when local Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail(
                "Graph mapping integration requires reachable Supabase Postgres"
            )
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    return connection


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one connection rolled back after each test."""

    connection = _require_postgres()
    yield connection
    connection.rollback()
    connection.close()


def _insert_auth_user(cursor: psycopg.Cursor, user_id: UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row."""

    cursor.execute(
        """
        INSERT INTO auth.users (
          id, instance_id, aud, role, email, encrypted_password,
          email_confirmed_at, created_at, updated_at
        )
        VALUES (
          %s,
          '00000000-0000-0000-0000-000000000000'::uuid,
          'authenticated',
          'authenticated',
          %s,
          crypt('test-password', gen_salt('bf')),
          timezone('utc', now()),
          timezone('utc', now()),
          timezone('utc', now())
        )
        ON CONFLICT (id) DO NOTHING
        """,
        (user_id, email),
    )


def _seed_graph_pending_document(
    connection: psycopg.Connection,
    *,
    language: str = "en",
    chunk_text: str = "canonical mapping passage",
) -> tuple[UUID, UUID, UUID, UUID]:
    """Insert one Hybrid-ready graph-pending document with a canonical chunk.

    Args:
        connection: Open Postgres connection.
        language: Version language.
        chunk_text: Canonical raw_text.

    Returns:
        ``(user_id, document_id, version_id, chunk_id)``.
    """

    admin = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_id = uuid4()
    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        _insert_auth_user(cursor, admin, f"{admin}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, mfa_enrolled)
            VALUES (%s, 'admin', true)
            """,
            (admin,),
        )
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by, graph_eligible)
            VALUES (%s, 'Mapping Doc', 'company_visible', %s, false)
            """,
            (document_id, admin),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, created_by, status, language,
              graph_eligible, hybrid_verified_at, content_hash
            )
            VALUES (
              %s, %s, 1, %s, 'graph_pending'::app.document_status, %s,
              true, timezone('utc', now()), %s
            )
            """,
            (version_id, document_id, admin, language, content_hash(chunk_text)),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s, graph_eligible = true
            WHERE id = %s
            """,
            (version_id, document_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text, content_hash
            )
            VALUES (%s, %s, %s, 0, %s, %s)
            """,
            (
                chunk_id,
                document_id,
                version_id,
                chunk_text,
                content_hash(chunk_text),
            ),
        )
    connection.execute("SET ROLE app_worker")
    return admin, document_id, version_id, chunk_id


def test_expand_columns_exist(db_connection: psycopg.Connection) -> None:
    """Packet 4 adds version/config/support columns without dropping keys."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'app'
              AND table_name IN (
                'lightrag_source_map',
                'lightrag_chunk_map',
                'graph_evidence_map'
              )
              AND column_name IN (
                'version_id',
                'workspace_key',
                'config_generation',
                'support',
                'pipeline_version'
              )
            """
        )
        names = {str(row[0]) for row in cursor.fetchall()}
    assert "version_id" in names
    assert "workspace_key" in names
    assert "config_generation" in names
    assert "support" in names
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'app'
              AND tablename IN ('graph_map_repair_jobs', 'graph_mapping_telemetry')
            """
        )
        tables = {str(row[0]) for row in cursor.fetchall()}
    assert tables == {"graph_map_repair_jobs", "graph_mapping_telemetry"}
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'app'
              AND indexname = 'lightrag_chunk_map_vendor_chunk_uq'
            """
        )
        index_row = cursor.fetchone()
    assert index_row is not None


def test_mapping_caller_rpc_avoids_worker_profile_table_grant(
    db_connection: psycopg.Connection,
) -> None:
    """Worker resolves one uploader through the RPC without profile SELECT."""

    user_id, _document_id, version_id, _chunk_id = _seed_graph_pending_document(
        db_connection
    )
    row = db_connection.execute(
        """
        SELECT user_id::text, role::text, authorization_version
        FROM app.load_graph_mapping_caller(%s)
        """,
        (version_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == str(user_id)
    assert row[1] == "admin"
    assert int(row[2]) >= 1
    db_connection.execute("SET ROLE postgres")
    privileges = db_connection.execute(
        """
        SELECT
          has_function_privilege(
            'app_worker',
            'app.load_graph_mapping_caller(uuid)',
            'EXECUTE'
          ),
          has_table_privilege('app_worker', 'app.profiles', 'SELECT')
        """
    ).fetchone()
    assert privileges == (True, False)


def _disable_commit(connection: psycopg.Connection) -> None:
    """Keep mapping writes in the test transaction so rollback can clean up.

    Args:
        connection: Open connection whose ``commit`` will become a no-op.
    """

    connection.commit = lambda: None  # type: ignore[method-assign]


def test_worker_can_write_maps_and_replay(
    db_connection: psycopg.Connection,
) -> None:
    """Worker RLS accepts map upserts and replay does not duplicate rows."""

    chunk_text = "canonical mapping passage"
    _admin, document_id, version_id, chunk_id = _seed_graph_pending_document(
        db_connection,
        chunk_text=chunk_text,
    )
    _disable_commit(db_connection)
    vendor_chunk_id = "vendor-chunk-1"
    source_id = canonical_passage_source_id(
        version_id=version_id,
        chunk_id=chunk_id,
    )
    enveloped = bind_graph_source_text(
        document_version_id=source_id,
        normalized_text=chunk_text,
    )
    vendor = _FakeVendor(
        chunks=[
            {
                "id": vendor_chunk_id,
                "full_doc_id": source_id,
                "content": enveloped,
            }
        ],
        nodes=[
            {
                "id": "Alpha",
                "properties": {
                    "entity_name": "Alpha",
                    "entity_type": "ORG",
                    "source_id": vendor_chunk_id,
                },
            },
            {
                "id": "Beta",
                "properties": {
                    "entity_name": "Beta",
                    "entity_type": "ORG",
                    "source_id": vendor_chunk_id,
                },
            },
        ],
        edges=[
            {
                "src_id": "Alpha",
                "tgt_id": "Beta",
                "properties": {
                    "keywords": "employs",
                    "source_id": vendor_chunk_id,
                },
            }
        ],
    )
    service = GraphMappingService(
        db_connection,
        vendor_reader=vendor,
        writer=_StubWriter(),
    )
    first = asyncio.run(
        service.map_after_vendor_success(
            document_id=document_id,
            version_id=version_id,
        )
    )
    assert first.maps_verified is True
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM app.document_versions WHERE id = %s",
            (version_id,),
        )
        status_row = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM app.lightrag_source_map WHERE document_id = %s",
            (document_id,),
        )
        source_count = cursor.fetchone()
        cursor.execute(
            """
            SELECT graph_object_id
            FROM app.graph_evidence_map
            WHERE version_id = %s AND graph_object_type = 'statement'
            """,
            (version_id,),
        )
        statement_ids = [str(row[0]) for row in cursor.fetchall()]
    assert status_row is not None
    assert str(status_row[0]) == "graph_ready"
    assert source_count is not None
    assert int(source_count[0]) == 1
    assert len(statement_ids) == 1
    db_connection.execute(
        """
        UPDATE app.document_versions
        SET status = 'graph_pending'::app.document_status
        WHERE id = %s
        """,
        (version_id,),
    )
    second = asyncio.run(
        service.map_after_vendor_success(
            document_id=document_id,
            version_id=version_id,
        )
    )
    assert second.maps_verified is True
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM app.lightrag_source_map WHERE document_id = %s",
            (document_id,),
        )
        replay_source = cursor.fetchone()
        cursor.execute(
            """
            SELECT graph_object_id
            FROM app.graph_evidence_map
            WHERE version_id = %s AND graph_object_type = 'statement'
            """,
            (version_id,),
        )
        replay_statements = [str(row[0]) for row in cursor.fetchall()]
    assert replay_source is not None
    assert int(replay_source[0]) == 1
    assert replay_statements == statement_ids


def test_processed_without_maps_stays_pending(
    db_connection: psycopg.Connection,
) -> None:
    """Vendor PROCESSED alone cannot contribute to Graph Ready."""

    _admin, document_id, version_id, _chunk_id = _seed_graph_pending_document(
        db_connection
    )
    _disable_commit(db_connection)
    vendor = _FakeVendor(
        chunks=[],
    )
    service = GraphMappingService(
        db_connection,
        vendor_reader=vendor,
        writer=_StubWriter(),
    )
    outcome = asyncio.run(
        service.map_after_vendor_success(
            document_id=document_id,
            version_id=version_id,
        )
    )
    assert outcome.maps_verified is False
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM app.document_versions WHERE id = %s",
            (version_id,),
        )
        row = cursor.fetchone()
        cursor.execute(
            """
            SELECT count(*)
            FROM app.graph_map_repair_jobs
            WHERE version_id = %s
            """,
            (version_id,),
        )
        repairs = cursor.fetchone()
    assert row is not None
    assert str(row[0]) == "graph_pending"
    assert repairs is not None
    assert int(repairs[0]) >= 1
