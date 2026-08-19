"""Keyset pagination bounds for document and conversation lists (PRD-M-022)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

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


def test_list_visible_documents_page_is_keyset_bounded(
    db_connection: psycopg.Connection,
) -> None:
    """Default/max caps apply and a created_at,id cursor returns the next page."""

    owner_id = uuid4()
    first_id = uuid4()
    second_id = uuid4()
    third_id = uuid4()
    stamp = datetime.now(tz=UTC) + timedelta(days=36500)

    with db_connection.cursor() as cursor:
        _insert_profile(cursor, user_id=owner_id, role="owner")
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by, created_at)
            VALUES
              (%s, 'Page one', 'company_visible', %s, %s),
              (%s, 'Page two', 'company_visible', %s, %s),
              (%s, 'Page three', 'company_visible', %s, %s)
            """,
            (
                first_id,
                owner_id,
                stamp,
                second_id,
                owner_id,
                stamp - timedelta(seconds=1),
                third_id,
                owner_id,
                stamp - timedelta(seconds=2),
            ),
        )
        authz = _auth_version(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT id
            FROM app.list_visible_documents_page(%s, %s, %s, %s, NULL, NULL)
            """,
            (owner_id, "owner", authz, 2),
        )
        page = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT id
            FROM app.list_visible_documents_page(%s, %s, %s, %s, %s, %s)
            """,
            (owner_id, "owner", authz, 2, stamp - timedelta(seconds=1), second_id),
        )
        next_page = [row[0] for row in cursor.fetchall()]
        cursor.execute("SAVEPOINT half_cursor")
        with pytest.raises(psycopg.errors.RaiseException, match="invalid_cursor"):
            cursor.execute(
                """
                SELECT id
                FROM app.list_visible_documents_page(%s, %s, %s, %s, %s, NULL)
                """,
                (owner_id, "owner", authz, 2, stamp),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT half_cursor")
        cursor.execute("RELEASE SAVEPOINT half_cursor")
        cursor.execute(
            """
            SELECT count(*)
            FROM app.list_visible_documents(%s, %s, %s)
            """,
            (owner_id, "owner", authz),
        )
        bounded = cursor.fetchone()

    assert page == [first_id, second_id]
    assert third_id in next_page
    assert bounded is not None
    assert int(bounded[0]) <= 50


def test_profiles_update_self_freezes_capability_columns(
    db_connection: psycopg.Connection,
) -> None:
    """Self-update WITH CHECK freezes upload_enabled, mfa_enrolled, and disabled_at."""

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pg_get_expr(polwithcheck, polrelid)
            FROM pg_policy
            WHERE polname = 'profiles_update_self_non_role'
            """
        )
        row = cursor.fetchone()
    assert row is not None
    check_sql = str(row[0])
    assert "upload_enabled" in check_sql
    assert "mfa_enrolled" in check_sql
    assert "disabled_at" in check_sql
