"""Upload finalization RPC contract tests."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from smart_rag_api.services.upload_finalize import (
    DuplicateContentError,
    UploadFinalizeRequest,
    finalize_quarantine_upload,
)

from tests.contract.integration_support import require_supabase_db_url, try_connect


def insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one minimal auth user."""

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


def read_authorization_version(cursor: psycopg.Cursor) -> int:
    """Return live authorization version."""

    cursor.execute("SELECT app.current_authorization_version()")
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one Postgres connection or skip when Supabase is unreachable."""

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_finalize_quarantine_upload_idempotent_and_wrong_path_denied(
    db_connection: psycopg.Connection,
) -> None:
    """Finalize creates one job; cross-user reservation access is rejected."""

    user_id = uuid.uuid4()
    other_id = uuid.uuid4()
    content = b"synthetic-fixture"
    digest = hashlib.sha256(content).hexdigest()
    with db_connection.cursor() as cursor:
        insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        insert_auth_user(cursor, other_id, f"{other_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'member', true, true), (%s, 'member', true, true)
            """,
            (user_id, other_id),
        )
        auth_version = read_authorization_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT reservation_id
            FROM app.reserve_upload_quota(
              %s, 'member', %s, %s, 'finalize-idem', 'sess', NULL
            )
            """,
            (user_id, auth_version, len(content)),
        )
        reservation_row = cursor.fetchone()
        assert reservation_row is not None
        reservation_id = reservation_row[0]
        cursor.execute(
            """
            SELECT status
            FROM app.finalize_upload_quota(%s, 'member', %s, %s, %s)
            """,
            (user_id, auth_version, reservation_id, len(content)),
        )
        assert cursor.fetchone() is not None
        object_name = f"{user_id}/{reservation_id}/sample.txt"
        cursor.execute(
            """
            SELECT document_id, version_id, job_id
            FROM app.finalize_quarantine_upload(
              %s, 'member', %s, %s, %s, %s, %s,
              'text/plain', 'allowed', '2026-08-13', 'job-idem-1', 'Sample'
            )
            """,
            (user_id, auth_version, reservation_id, object_name, digest, len(content)),
        )
        first = cursor.fetchone()
        assert first is not None
        cursor.execute(
            """
            SELECT document_id, version_id, job_id
            FROM app.finalize_quarantine_upload(
              %s, 'member', %s, %s, %s, %s, %s,
              'text/plain', 'allowed', '2026-08-13', 'job-idem-1', 'Sample'
            )
            """,
            (user_id, auth_version, reservation_id, object_name, digest, len(content)),
        )
        second = cursor.fetchone()
        assert second == first

        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT dv.status
            FROM app.document_versions AS dv
            WHERE dv.id = %s
            """,
            (first[1],),
        )
        status_row = cursor.fetchone()
        assert status_row is not None
        assert status_row[0] == "uploaded"

        cursor.execute("SAVEPOINT wrong_user")
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                SELECT document_id
                FROM app.finalize_quarantine_upload(
                  %s, 'member', %s, %s, %s, %s, %s,
                  'text/plain', 'allowed', '2026-08-13', 'job-idem-2', 'Sample'
                )
                """,
                (
                    other_id,
                    auth_version,
                    reservation_id,
                    object_name,
                    digest,
                    len(content),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT wrong_user")
        cursor.execute("RELEASE SAVEPOINT wrong_user")


def test_reserve_creates_uploading_version_before_finalize(
    db_connection: psycopg.Connection,
) -> None:
    """Quota reserve creates an observable ``uploading`` version before bytes land."""

    user_id = uuid.uuid4()
    with db_connection.cursor() as cursor:
        insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'member', true, true)
            """,
            (user_id,),
        )
        auth_version = read_authorization_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT reservation_id, document_id, version_id
            FROM app.reserve_upload_quota(
              %s, 'member', %s, 512, 'upload-status', 'sess', NULL
            )
            """,
            (user_id, auth_version),
        )
        reserved = cursor.fetchone()
        assert reserved is not None
        reservation_id, document_id, version_id = reserved
        assert document_id is not None
        assert version_id is not None
        cursor.execute("RESET ROLE")
        cursor.execute(
            "SELECT status FROM app.document_versions WHERE id = %s",
            (version_id,),
        )
        status_row = cursor.fetchone()
        assert status_row is not None
        assert status_row[0] == "uploading"
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT reservation_id, document_id, version_id
            FROM app.reserve_upload_quota(
              %s, 'member', %s, 512, 'upload-status', 'sess', NULL
            )
            """,
            (user_id, auth_version),
        )
        replay = cursor.fetchone()
        assert replay == (reservation_id, document_id, version_id)


def _purge_upload_user(url: str, user_id: uuid.UUID) -> None:
    """Delete rows created by one committed upload-finalize fixture user.

    Args:
        url: Local Supabase DSN.
        user_id: Auth user inserted by the test.
    """

    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("SET ROLE postgres")
        docs = connection.execute(
            "SELECT id FROM app.documents WHERE created_by = %s",
            (user_id,),
        ).fetchall()
        doc_ids = [row[0] for row in docs]
        if doc_ids:
            connection.execute(
                "UPDATE app.documents SET current_version_id = NULL WHERE id = ANY(%s)",
                (doc_ids,),
            )
            connection.execute(
                "DELETE FROM app.ingestion_jobs WHERE document_id = ANY(%s)",
                (doc_ids,),
            )
            connection.execute(
                "DELETE FROM app.document_sources WHERE document_id = ANY(%s)",
                (doc_ids,),
            )
            connection.execute(
                "DELETE FROM app.document_versions WHERE document_id = ANY(%s)",
                (doc_ids,),
            )
            connection.execute(
                "DELETE FROM app.documents WHERE id = ANY(%s)",
                (doc_ids,),
            )
        connection.execute(
            "DELETE FROM app.upload_quota_reservations WHERE user_id = %s",
            (user_id,),
        )
        connection.execute("DELETE FROM app.profiles WHERE user_id = %s", (user_id,))
        connection.execute("DELETE FROM auth.users WHERE id = %s", (user_id,))


def _finalize_uploaded_hash(
    cursor: psycopg.Cursor,
    *,
    user_id: uuid.UUID,
    auth_version: int,
    digest: str,
    content_len: int,
    idempotency_key: str,
) -> uuid.UUID:
    """Reserve and SQL-finalize one uploaded document.

    Args:
        cursor: Open cursor already allowed to call ``app_api`` functions.
        user_id: Owner subject.
        auth_version: Live authorization snapshot.
        digest: Content hash.
        content_len: Byte length.
        idempotency_key: Unique job key.

    Returns:
        Created document id.
    """

    cursor.execute("SET ROLE app_api")
    cursor.execute(
        """
        SELECT reservation_id
        FROM app.reserve_upload_quota(
          %s, 'owner', %s, %s, %s, 'sess', NULL
        )
        """,
        (user_id, auth_version, content_len, idempotency_key),
    )
    reservation = cursor.fetchone()
    assert reservation is not None
    object_name = f"{user_id}/{reservation[0]}/sample.txt"
    cursor.execute(
        """
        SELECT document_id
        FROM app.finalize_quarantine_upload(
          %s, 'owner', %s, %s, %s, %s, %s,
          'text/plain', 'allowed', '2026-08-13', %s, 'Sample'
        )
        """,
        (
            user_id,
            auth_version,
            reservation[0],
            object_name,
            digest,
            content_len,
            idempotency_key,
        ),
    )
    created = cursor.fetchone()
    assert created is not None
    return uuid.UUID(str(created[0]))


def test_duplicate_content_hash_rejected_for_visible_document(
    db_connection: psycopg.Connection,
) -> None:
    """A second finalize of a visible hash raises DuplicateContentError."""

    url = require_supabase_db_url()
    user_id = uuid.uuid4()
    digest = hashlib.sha256(b"duplicate-visible-hash").hexdigest()
    try:
        with db_connection.cursor() as cursor:
            insert_auth_user(cursor, user_id, f"{user_id}@example.com")
            cursor.execute(
                """
                INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
                VALUES (%s, 'owner', true, true)
                """,
                (user_id,),
            )
            auth_version = read_authorization_version(cursor)
            _finalize_uploaded_hash(
                cursor,
                user_id=user_id,
                auth_version=auth_version,
                digest=digest,
                content_len=len(b"duplicate-visible-hash"),
                idempotency_key=f"dup-{user_id}",
            )
        db_connection.commit()
        with pytest.raises(DuplicateContentError):
            finalize_quarantine_upload(
                url,
                caller_user_id=user_id,
                caller_role="owner",
                caller_authorization_version=auth_version,
                request=UploadFinalizeRequest(
                    reservation_id=uuid.uuid4(),
                    object_name=f"{user_id}/unused/sample.txt",
                    content_hash=digest,
                    actual_bytes=8,
                    media_type="text/plain",
                    declared_category="allowed",
                    attestation_policy_version="2026-08-13",
                    idempotency_key=f"dup-again-{user_id}",
                ),
            )
    finally:
        _purge_upload_user(url, user_id)


def test_deleted_document_hash_can_be_uploaded_again(
    db_connection: psycopg.Connection,
) -> None:
    """Soft-delete clears the hash guard so the same bytes can finalize."""

    url = require_supabase_db_url()
    user_id = uuid.uuid4()
    content = b"reupload-after-delete"
    digest = hashlib.sha256(content).hexdigest()
    try:
        with db_connection.cursor() as cursor:
            insert_auth_user(cursor, user_id, f"{user_id}@example.com")
            cursor.execute(
                """
                INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
                VALUES (%s, 'owner', true, true)
                """,
                (user_id,),
            )
            auth_version = read_authorization_version(cursor)
            document_id = _finalize_uploaded_hash(
                cursor,
                user_id=user_id,
                auth_version=auth_version,
                digest=digest,
                content_len=len(content),
                idempotency_key=f"reup-{user_id}",
            )
            cursor.execute("RESET ROLE")
            cursor.execute(
                "SELECT app.delete_visible_document(%s::uuid, 'owner', %s::bigint, %s::uuid)",
                (user_id, auth_version, document_id),
            )
            deleted = cursor.fetchone()
            assert deleted is not None
            assert deleted[0] == document_id
            auth_version = read_authorization_version(cursor)
            cursor.execute("SET ROLE app_api")
            cursor.execute(
                """
                SELECT reservation_id
                FROM app.reserve_upload_quota(
                  %s, 'owner', %s, %s, %s, 'sess', NULL
                )
                """,
                (user_id, auth_version, len(content), f"reup2-{user_id}"),
            )
            reservation = cursor.fetchone()
            assert reservation is not None
        db_connection.commit()
        outcome = finalize_quarantine_upload(
            url,
            caller_user_id=user_id,
            caller_role="owner",
            caller_authorization_version=auth_version,
            request=UploadFinalizeRequest(
                reservation_id=reservation[0],
                object_name=f"{user_id}/{reservation[0]}/sample.txt",
                content_hash=digest,
                actual_bytes=len(content),
                media_type="text/plain",
                declared_category="allowed",
                attestation_policy_version="2026-08-13",
                idempotency_key=f"reup2-{user_id}",
                document_title="Sample",
            ),
        )
        assert outcome.document_id != document_id
    finally:
        _purge_upload_user(url, user_id)
