"""Historical citation GET rechecks ACL and current version (PRD-M-013)."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.query_admission.service import list_run_citations

from tests.contract.integration_support import resolve_supabase_db_url, try_connect
from tests.contract.test_query_run_admission import (
    admit,
    authorization_version,
    caller_context,
    insert_conversation,
    insert_user_profile,
)


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


def test_citation_get_marks_unavailable_after_acl_revoke(
    db_connection: psycopg.Connection,
) -> None:
    """After ACL downgrade, citation GET omits ``chunk_id`` and flags unavailable."""

    owner_id = uuid4()
    member_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_id = uuid4()

    with db_connection.cursor() as cursor:
        insert_user_profile(cursor, user_id=owner_id, role="owner")
        insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = insert_conversation(cursor, user_id=member_id)
        cursor.execute(
            """
            INSERT INTO app.documents (
              id, title, visibility, created_by
            )
            VALUES (%s, 'Restricted citation fixture', 'restricted', %s)
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
            UPDATE app.documents
            SET current_version_id = %s
            WHERE id = %s
            """,
            (version_id, document_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text
            )
            VALUES (%s, %s, %s, 0, 'restricted passage')
            """,
            (chunk_id, document_id, version_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_acl (
              document_id, grantee_user_id, granted_by
            )
            VALUES (%s, %s, %s)
            """,
            (document_id, member_id, owner_id),
        )
        authz = authorization_version(cursor)

    member = caller_context(member_id, "member", authz)
    admitted, _ = admit(
        db_connection,
        caller=member,
        conversation_id=conversation_id,
    )
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO app.citations (
              run_id, citation_index, chunk_id, snippet, provenance
            )
            VALUES (%s, 0, %s, 'must not leak', '{}'::jsonb)
            """,
            (admitted.context.run_id, chunk_id),
        )
        owner = caller_context(owner_id, "owner", authorization_version(cursor))
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT private.set_document_acl(%s, %s, %s, %s, %s, %s)
            """,
            (
                owner.user_id,
                owner.rpc_role(),
                owner.rpc_authorization_version(),
                document_id,
                member_id,
                False,
            ),
        )
        cursor.execute("RESET ROLE")
        authz_after = authorization_version(cursor)

    member_after = caller_context(member_id, "member", authz_after)
    db_connection.execute("SET ROLE app_api")
    try:
        records = list_run_citations(
            db_connection,
            caller=member_after,
            run_id=admitted.context.run_id,
        )
    finally:
        db_connection.execute("RESET ROLE")

    assert len(records) == 1
    assert records[0].source_unavailable is True
    assert records[0].chunk_id is None
    assert UUID(str(records[0].citation_id))
