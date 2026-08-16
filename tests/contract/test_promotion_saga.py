"""Promotion saga crash/replay contract tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import replace

import psycopg
import pytest
from smart_rag_core.gateways.storage import StorageGateway, StorageObjectMetadata
from smart_rag_core.ingestion.promotion import (
    PromotionContext,
    PromotionSaga,
    PromotionSagaError,
    PromotionStep,
)

from tests.contract.integration_support import resolve_supabase_db_url, try_connect


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one Postgres connection or skip when Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_promotion_saga_replays_after_each_crash_point(
    db_connection: psycopg.Connection,
) -> None:
    """Injected crashes resume to one completed saga."""

    calls: list[str] = []

    class _Storage(StorageGateway):
        """Recording Storage gateway that never contacts the provider."""

        def copy_object(self, **kwargs: object) -> None:
            """Record a copy call without performing Storage I/O."""

            del kwargs
            calls.append("copy")

        def verify_object(self, **kwargs: object) -> StorageObjectMetadata:
            """Record a verify call and return fixture metadata."""

            del kwargs
            calls.append("verify")
            return StorageObjectMetadata(
                bucket="documents-originals",
                path="documents/x/versions/y/a.txt",
                byte_size=5,
                content_hash_sha256="a" * 64,
                media_type="text/plain",
            )

        def delete_object(self, **kwargs: object) -> None:
            """Record a delete call without performing Storage I/O."""

            del kwargs
            calls.append("delete")

    storage = _Storage(
        supabase_url="http://example",
        admin_secret="test-fixture-secret",  # noqa: S106
    )
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    digest = "a" * 64
    with db_connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO app.documents (id, title) VALUES (%s, 'x')",
            (document_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, status,
              storage_bucket, storage_path, content_hash, byte_size
            )
            VALUES (
              %s, %s, 1, 'scanning',
              'documents-quarantine', 'q/a.txt', %s, 5
            )
            """,
            (version_id, document_id, digest),
        )
        db_connection.commit()

    context = PromotionContext(
        saga_idempotency_key=f"test-{uuid.uuid4()}",
        version_id=version_id,
        reservation_id=None,
        quarantine_bucket="documents-quarantine",
        quarantine_path="q/a.txt",
        destination_bucket="documents-originals",
        destination_path="documents/x/versions/y/a.txt",
        expected_hash=digest,
        expected_bytes=5,
    )

    for step in (
        PromotionStep.INTENT,
        PromotionStep.COPY_DONE,
        PromotionStep.VERIFY_DONE,
        PromotionStep.DB_SWITCHED,
    ):
        db_connection.execute("SET ROLE app_worker")
        saga = PromotionSaga(db_connection, storage)
        with pytest.raises(PromotionSagaError):
            saga.run(replace(context, crash_after=step))
        db_connection.rollback()

    db_connection.execute("SET ROLE app_worker")
    result = PromotionSaga(db_connection, storage).run(context)
    db_connection.commit()
    assert result.final_step is PromotionStep.COMPLETED
    assert calls.count("copy") >= 1
    assert calls.count("verify") >= 1
    assert calls.count("delete") >= 1
