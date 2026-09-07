"""Contract tests for authorized rerank context and parent expansion."""

from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.retrieval.context_loader import fetch_authorized_chunk_context
from smart_rag_core.retrieval.profiles import RERANK_POOL_SIZE

from tests.contract.hybrid_retrieval_seed import (
    HybridRetrievalSeed,
    seed_hybrid_retrieval_fixture,
)
from tests.contract.integration_support import require_supabase_db_url, try_connect


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield Postgres or skip when local Supabase is unreachable."""

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def seed(db_connection: psycopg.Connection) -> HybridRetrievalSeed:
    """Commit one retrieval fixture on the live local database."""

    return seed_hybrid_retrieval_fixture(db_connection)


def test_context_rpc_returns_raw_text_and_drops_restricted(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Members receive canonical raw_text; restricted IDs are omitted."""

    visible = seed.visible_chunk_ids[0]
    rows = fetch_authorized_chunk_context(
        db_connection,
        caller=seed.member,
        chunk_ids=(visible, seed.restricted_chunk_id, seed.deleted_chunk_id),
    )
    returned = {item.chunk_id for item in rows}
    assert visible in returned
    assert seed.restricted_chunk_id not in returned
    assert seed.deleted_chunk_id not in returned
    raw = next(item.raw_text for item in rows if item.chunk_id == visible)
    assert seed.token in raw
    assert "body_search" not in raw
    assert RERANK_POOL_SIZE == 20


def test_context_rpc_loads_parent_when_authorized(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Parent rows that are current and ACL-visible survive expansion fetch."""

    parent_id = uuid4()
    child_id = seed.visible_chunk_ids[1]
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text,
              is_search_representative
            )
            VALUES (%s, %s, %s, 40, %s, false)
            """,
            (
                parent_id,
                seed.visible_document_id,
                seed.visible_version_id,
                f"parent heading {seed.token}",
            ),
        )
        cursor.execute(
            """
            UPDATE app.document_chunks
            SET parent_chunk_id = %s
            WHERE id = %s
            """,
            (parent_id, child_id),
        )
    db_connection.commit()
    rows = fetch_authorized_chunk_context(
        db_connection,
        caller=seed.member,
        chunk_ids=(child_id, parent_id),
    )
    by_id = {item.chunk_id: item for item in rows}
    assert child_id in by_id
    assert parent_id in by_id
    assert by_id[parent_id].is_search_representative is False
    assert seed.token in by_id[parent_id].raw_text
    restricted_parent = fetch_authorized_chunk_context(
        db_connection,
        caller=seed.member,
        chunk_ids=(seed.restricted_chunk_id,),
    )
    assert restricted_parent == ()


def test_context_rpc_round_trips_sheet_and_url_from_provenance(
    db_connection: psycopg.Connection,
    seed: HybridRetrievalSeed,
) -> None:
    """Provenance locators supply sheet, range, and URL on authorized rows."""

    visible = seed.visible_chunk_ids[0]
    provenance = {
        "locators": [
            {
                "format": "xlsx",
                "sheet_name": "Hours",
                "range_ref": "B2:D10",
                "cell_ref": "B2",
            },
            {
                "format": "html",
                "source_url": "https://example.invalid/leave-policy",
            },
        ]
    }
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.document_chunks
            SET
              provenance = %s::jsonb,
              page_number = 7,
              section_path = ARRAY['Payroll', 'Overtime']
            WHERE id = %s
            """,
            (json.dumps(provenance), visible),
        )
    db_connection.commit()
    rows = fetch_authorized_chunk_context(
        db_connection,
        caller=seed.member,
        chunk_ids=(visible,),
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.page_number == 7
    assert row.section_path == ("Payroll", "Overtime")
    assert row.sheet_name == "Hours"
    assert row.range_ref == "B2:D10"
    assert row.source_url == "https://example.invalid/leave-policy"
    assert seed.token in row.raw_text
