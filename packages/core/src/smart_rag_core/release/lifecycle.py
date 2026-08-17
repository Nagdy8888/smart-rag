"""Real RPC/CAS drivers for admission, scan/parse, failed, and deletion states."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

import psycopg


def insert_auth_user(cursor: psycopg.Cursor, user_id: UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row.

    Args:
        cursor: Open cursor.
        user_id: Auth user id.
        email: Unique email.
    """

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
    """Return the live authorization version.

    Args:
        cursor: Open cursor.

    Returns:
        Authorization version integer.
    """

    cursor.execute("SELECT app.current_authorization_version()")
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("authorization version missing")
    return int(row[0])


def drive_uploading(connection: psycopg.Connection) -> tuple[UUID, UUID, UUID]:
    """Reserve upload quota so a version is observable as ``uploading``.

    Args:
        connection: Superuser-capable connection.

    Returns:
        ``(user_id, document_id, version_id)``.
    """

    user_id = uuid4()
    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
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
              %s, 'member', %s, %s, %s, 'phase09-sess', NULL
            )
            """,
            (user_id, auth_version, 32, f"phase09-uploading-{user_id}"),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("reserve_upload_quota returned no row")
    document_id = UUID(str(row[1]))
    version_id = UUID(str(row[2]))
    connection.commit()
    return user_id, document_id, version_id


def drive_uploaded(connection: psycopg.Connection) -> tuple[UUID, UUID, UUID]:
    """Finalize a quarantine upload so the version is ``uploaded``.

    Args:
        connection: Superuser-capable connection.

    Returns:
        ``(user_id, document_id, version_id)``.
    """

    user_id = uuid4()
    content = b"phase09-uploaded-fixture"
    digest = hashlib.sha256(content).hexdigest()
    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
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
            SELECT reservation_id
            FROM app.reserve_upload_quota(
              %s, 'member', %s, %s, %s, 'phase09-uploaded-sess', NULL
            )
            """,
            (user_id, auth_version, len(content), f"phase09-uploaded-{user_id}"),
        )
        reserved = cursor.fetchone()
        if reserved is None:
            raise RuntimeError("reserve_upload_quota returned no reservation")
        reservation_id = reserved[0]
        cursor.execute(
            """
            SELECT status
            FROM app.finalize_upload_quota(%s, 'member', %s, %s, %s)
            """,
            (user_id, auth_version, reservation_id, len(content)),
        )
        object_name = f"{user_id}/{reservation_id}/phase09.txt"
        cursor.execute(
            """
            SELECT document_id, version_id, job_id
            FROM app.finalize_quarantine_upload(
              %s, 'member', %s, %s, %s, %s, %s,
              'text/plain', 'allowed', '2026-08-17', %s, 'Phase09 Uploaded'
            )
            """,
            (
                user_id,
                auth_version,
                reservation_id,
                object_name,
                digest,
                len(content),
                f"phase09-job-{user_id}",
            ),
        )
        finalized = cursor.fetchone()
    if finalized is None:
        raise RuntimeError("finalize_quarantine_upload returned no row")
    document_id = UUID(str(finalized[0]))
    version_id = UUID(str(finalized[1]))
    connection.commit()
    return user_id, document_id, version_id


def transition_status(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
    expected: str,
    new_status: str,
) -> None:
    """Apply the worker CAS used by scan/parse graphs.

    Args:
        connection: Worker-capable connection.
        version_id: Version to transition.
        expected: Expected current public status.
        new_status: Target public status.

    Raises:
        RuntimeError: If the CAS does not update exactly one row.
    """

    connection.execute("SET ROLE app_worker")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT app.transition_document_version_status(
              %s, %s::app.document_status, %s::app.document_status
            )
            """,
            (version_id, expected, new_status),
        )
        row = cursor.fetchone()
    if row is None or row[0] is not True:
        raise RuntimeError(
            f"status CAS failed {expected}->{new_status} for {version_id}"
        )
    connection.commit()


def drive_scanning(connection: psycopg.Connection) -> tuple[UUID, UUID]:
    """Reach ``scanning`` through the same CAS as ``scan_graph.mark_scanning``.

    Args:
        connection: Superuser-capable connection.

    Returns:
        ``(document_id, version_id)``.
    """

    _user_id, document_id, version_id = drive_uploaded(connection)
    transition_status(
        connection,
        version_id=version_id,
        expected="uploaded",
        new_status="scanning",
    )
    return document_id, version_id


def drive_parsing(connection: psycopg.Connection) -> tuple[UUID, UUID]:
    """Reach ``parsing`` through the same CAS as ``index_graph.mark_parsing``.

    Args:
        connection: Superuser-capable connection.

    Returns:
        ``(document_id, version_id)``.
    """

    document_id, version_id = drive_scanning(connection)
    transition_status(
        connection,
        version_id=version_id,
        expected="scanning",
        new_status="parsing",
    )
    return document_id, version_id


def drive_failed(connection: psycopg.Connection) -> tuple[UUID, UUID]:
    """Reach public ``failed`` via the scan/parse CAS after ``scanning``.

    The LangGraph currently returns ``index_failed`` / ``parse_failed`` in
    graph state without always writing this public status. Packet 1 proves
    the documented public state using the same ``transition_document_version_status``
    RPC the worker uses for scanning and parsing.

    Args:
        connection: Superuser-capable connection.

    Returns:
        ``(document_id, version_id)``.
    """

    document_id, version_id = drive_scanning(connection)
    transition_status(
        connection,
        version_id=version_id,
        expected="scanning",
        new_status="failed",
    )
    return document_id, version_id


def drive_deletion_pending(
    connection: psycopg.Connection,
    *,
    version_id: UUID,
) -> None:
    """Mark a version deletion-pending through the retrieval exclusion RPC.

    Args:
        connection: Worker-capable connection.
        version_id: Version to exclude.
    """

    connection.execute("SET ROLE app_worker")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT app.exclude_version_from_retrieval(%s, 'phase09_delete')",
            (version_id,),
        )
    connection.commit()


def read_version_status(connection: psycopg.Connection, version_id: UUID) -> str:
    """Return the public document status for one version.

    Args:
        connection: Open connection.
        version_id: Canonical version.

    Returns:
        Status enum text.
    """

    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM app.document_versions WHERE id = %s",
            (version_id,),
        )
        row = cursor.fetchone()
    if row is None:
        return "missing"
    return str(row[0])
