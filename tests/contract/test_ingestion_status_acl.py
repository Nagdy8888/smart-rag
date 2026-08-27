"""ACL contract for ingestion status RPC (PRD-C-010)."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest

from tests.contract.integration_support import resolve_supabase_db_url, try_connect
from tests.contract.test_rls_matrix import _auth_version, _insert_profile


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield a rollback Postgres connection or skip when local Supabase is down."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_member_cannot_read_restricted_version_status_by_id(
    db_connection: psycopg.Connection,
) -> None:
    """Guessing a restricted ``version_id`` returns no status row (HTTP 404)."""

    owner_id = uuid4()
    member_a = uuid4()
    member_b = uuid4()
    document_id = uuid4()
    version_id = uuid4()

    with db_connection.cursor() as cursor:
        _insert_profile(cursor, user_id=owner_id, role="owner")
        _insert_profile(cursor, user_id=member_a, role="member")
        _insert_profile(cursor, user_id=member_b, role="member")
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES (%s, 'Restricted status fixture', 'restricted', %s)
            """,
            (document_id, owner_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, created_by
            )
            VALUES (%s, %s, 1, %s)
            """,
            (version_id, document_id, owner_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_acl (
              document_id, grantee_user_id, granted_by
            )
            VALUES (%s, %s, %s)
            """,
            (document_id, member_a, owner_id),
        )
        authz = _auth_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT status_payload
            FROM app.get_version_ingestion_status(
              %s::uuid, %s::text, %s::bigint, %s::uuid
            )
            """,
            (member_a, "member", authz, version_id),
        )
        granted = cursor.fetchone()
        cursor.execute(
            """
            SELECT status_payload
            FROM app.get_version_ingestion_status(
              %s::uuid, %s::text, %s::bigint, %s::uuid
            )
            """,
            (member_b, "member", authz, version_id),
        )
        denied = cursor.fetchone()
        cursor.execute(
            """
            SELECT status_payload
            FROM app.get_version_ingestion_status(
              %s::uuid, %s::text, %s::bigint, %s::uuid
            )
            """,
            (owner_id, "owner", authz, version_id),
        )
        owner_row = cursor.fetchone()

    assert granted is not None
    payload = granted[0]
    assert isinstance(payload, dict)
    assert UUID(str(payload["version_id"])) == version_id
    assert denied is None
    assert owner_row is not None
