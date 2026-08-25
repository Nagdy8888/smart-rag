"""RLS matrix and identity propagation contract tests (Phase 2 Packet 3)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from tests.contract.integration_support import (
    refuse_hosted_destructive_dsn,
    resolve_supabase_db_url,
    try_connect,
)


def _insert_auth_user(cursor: psycopg.Cursor, user_id: uuid.UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row for profile FK tests."""

    cursor.execute(
        """
        INSERT INTO auth.users (
          id,
          instance_id,
          aud,
          role,
          email,
          encrypted_password,
          email_confirmed_at,
          created_at,
          updated_at
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


def _auth_version(cursor: psycopg.Cursor) -> int:
    """Read the current server-owned authorization generation.

    Args:
        cursor: Open test transaction cursor.

    Returns:
        Current monotonically increasing authorization version.
    """

    cursor.execute("SELECT app.current_authorization_version()")
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _insert_profile(
    cursor: psycopg.Cursor,
    *,
    user_id: uuid.UUID,
    role: str,
    upload_enabled: bool = False,
    mfa_enrolled: bool = False,
    disabled: bool = False,
) -> None:
    """Insert one Auth user and authoritative profile for matrix tests.

    Args:
        cursor: Open test transaction cursor.
        user_id: Stable test subject identifier.
        role: Authoritative ``app.user_role`` value.
        upload_enabled: Whether the member has upload capability.
        mfa_enrolled: Whether the profile records MFA enrollment.
        disabled: Whether the profile is inactive.
    """

    _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
    cursor.execute(
        """
        INSERT INTO app.profiles (
          user_id,
          role,
          upload_enabled,
          mfa_enrolled,
          disabled_at
        )
        VALUES (
          %s,
          %s::app.user_role,
          %s,
          %s,
          CASE WHEN %s THEN timezone('utc', now()) ELSE NULL END
        )
        """,
        (user_id, role, upload_enabled, mfa_enrolled, disabled),
    )


def _assert_fixture_document_visibility(
    visible: set[uuid.UUID],
    *,
    company_document: uuid.UUID,
    restricted_document: uuid.UUID,
    role_name: str,
) -> None:
    """Assert this test's fixtures follow the role matrix on a seeded database.

    The Phase 9 candidate seed may add other ``company_visible`` documents.
    Extra authorized rows do not weaken the fixture checks. A disabled caller
    must still see zero documents, including seed rows.

    Args:
        visible: IDs returned by ``app.list_visible_documents``.
        company_document: Fixture company-visible document.
        restricted_document: Fixture restricted document.
        role_name: Matrix cell name (``owner``, ``admin``, ``member``,
            ``upload_member``, ``viewer``, or ``disabled``).
    """

    if role_name == "disabled":
        assert not visible
        return
    assert company_document in visible
    if role_name in {"owner", "admin"}:
        assert restricted_document in visible
    else:
        assert restricted_document not in visible


def _visible_document_ids(
    cursor: psycopg.Cursor,
    user_id: uuid.UUID | None,
    role: str | None,
    authorization_version: int | None,
) -> set[uuid.UUID]:
    """Return document IDs exposed by the typed application RPC.

    Args:
        cursor: Open cursor currently using ``app_api``.
        user_id: Explicit server-derived caller subject, or ``None``.
        role: Explicit server-derived caller role, or ``None``.
        authorization_version: Explicit server-derived snapshot, or ``None``.

    Returns:
        IDs returned by ``app.list_visible_documents``.
    """

    cursor.execute(
        """
        SELECT id
        FROM app.list_visible_documents(%s, %s, %s)
        """,
        (user_id, role, authorization_version),
    )
    return {row[0] for row in cursor.fetchall()}


def _conversation_ids(
    cursor: psycopg.Cursor,
    user_id: uuid.UUID | None,
    role: str | None,
    authorization_version: int | None,
) -> set[uuid.UUID]:
    """Return conversation IDs exposed by the typed application RPC.

    Args:
        cursor: Open cursor currently using ``app_api``.
        user_id: Explicit server-derived caller subject, or ``None``.
        role: Explicit server-derived caller role, or ``None``.
        authorization_version: Explicit server-derived snapshot, or ``None``.

    Returns:
        IDs returned by ``app.list_user_conversations``.
    """

    cursor.execute(
        """
        SELECT id
        FROM app.list_user_conversations(%s, %s, %s)
        """,
        (user_id, role, authorization_version),
    )
    return {row[0] for row in cursor.fetchall()}


def _set_document_acl(
    cursor: psycopg.Cursor,
    *,
    caller_user_id: uuid.UUID,
    caller_role: str,
    authorization_version: int,
    document_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    grant: bool,
) -> bool:
    """Invoke the private typed ACL mutation RPC.

    Args:
        cursor: Open cursor currently using ``app_api``.
        caller_user_id: Explicit server-derived actor subject.
        caller_role: Explicit server-derived actor role.
        authorization_version: Live company authorization snapshot.
        document_id: Restricted document being administered.
        grantee_user_id: Active profile receiving or losing access.
        grant: ``True`` to grant or ``False`` to revoke.

    Returns:
        Whether the call changed an active ACL grant.
    """

    cursor.execute(
        """
        SELECT private.set_document_acl(%s, %s, %s, %s, %s, %s)
        """,
        (
            caller_user_id,
            caller_role,
            authorization_version,
            document_id,
            grantee_user_id,
            grant,
        ),
    )
    row = cursor.fetchone()
    assert row is not None
    return bool(row[0])


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one Postgres connection or skip when Supabase is unreachable."""

    url = resolve_supabase_db_url()
    refuse_hosted_destructive_dsn(url)
    connection = try_connect(url)
    if connection is None:
        pytest.skip("Local Supabase fixture unreachable")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_rls_matrix_documents_conversations_and_audit(
    db_connection: psycopg.Connection,
) -> None:
    """Prove forged/stale RPC context, ACL, creator privacy, and audit immutability."""

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    restricted_doc = uuid.uuid4()
    visible_doc = uuid.uuid4()
    conversation_a = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_a, f"{user_a}@example.com")
        _insert_auth_user(cursor, user_b, f"{user_b}@example.com")

        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, display_name)
            VALUES
              (%s, 'member', 'User A'),
              (%s, 'member', 'User B')
            """,
            (user_a, user_b),
        )

        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES
              (%s, 'Restricted Doc', 'restricted', %s),
              (%s, 'Company Doc', 'company_visible', %s)
            """,
            (restricted_doc, user_a, visible_doc, user_a),
        )

        cursor.execute(
            """
            INSERT INTO app.conversations (id, creator_user_id, title)
            VALUES (%s, %s, 'Private thread')
            """,
            (conversation_a, user_a),
        )

        auth_version = _auth_version(cursor)

        cursor.execute("SET ROLE app_api")

        cursor.execute(
            """
            SELECT id
            FROM app.list_visible_documents(%s, 'member', %s)
            """,
            (user_a, auth_version),
        )
        visible_ids = {row[0] for row in cursor.fetchall()}
        assert visible_doc in visible_ids
        assert restricted_doc not in visible_ids

        cursor.execute(
            """
            SELECT id
            FROM app.list_visible_documents(%s, 'member', %s)
            """,
            (user_b, auth_version),
        )
        forged_ids = {row[0] for row in cursor.fetchall()}
        assert visible_doc in forged_ids
        assert restricted_doc not in forged_ids

        cursor.execute(
            """
            SELECT count(*)
            FROM app.list_visible_documents(%s, 'admin', %s)
            """,
            (user_b, auth_version),
        )
        forged_role_count = cursor.fetchone()
        assert forged_role_count is not None
        assert forged_role_count[0] == 0

        cursor.execute(
            """
            SELECT count(*)
            FROM app.list_visible_documents(%s, 'member', %s)
            """,
            (user_a, auth_version - 1),
        )
        stale_context_count = cursor.fetchone()
        assert stale_context_count is not None
        assert stale_context_count[0] == 0

        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            INSERT INTO app.document_acl (document_id, grantee_user_id, granted_by)
            VALUES (%s, %s, %s)
            """,
            (restricted_doc, user_a, user_a),
        )
        auth_version = _auth_version(cursor)

        cursor.execute("SET ROLE app_api")

        cursor.execute(
            """
            SELECT id
            FROM app.list_visible_documents(%s, 'member', %s)
            """,
            (user_a, auth_version),
        )
        granted_ids = {row[0] for row in cursor.fetchall()}
        assert restricted_doc in granted_ids

        cursor.execute(
            """
            SELECT id
            FROM app.list_user_conversations(%s, 'member', %s)
            """,
            (user_a, auth_version),
        )
        conv_ids = {row[0] for row in cursor.fetchall()}
        assert conversation_a in conv_ids

        cursor.execute(
            """
            SELECT id
            FROM app.list_user_conversations(%s, 'member', %s)
            """,
            (user_b, auth_version),
        )
        other_conv_ids = {row[0] for row in cursor.fetchall()}
        assert conversation_a not in other_conv_ids

        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_audit_writer")

        cursor.execute(
            """
            SELECT app.append_audit_event(
              'rls_matrix_test',
              %s,
              'member'::app.user_role,
              'document',
              %s,
              %s,
              '{}'::jsonb
            )
            """,
            (user_a, visible_doc, auth_version),
        )
        audit_row = cursor.fetchone()
        assert audit_row is not None
        audit_id = audit_row[0]

        with pytest.raises(
            (psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)
        ):
            cursor.execute("SAVEPOINT audit_writer_update")
            cursor.execute(
                "UPDATE app.audit_events SET event_type = 'mutated' WHERE id = %s",
                (audit_id,),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_writer_update")
        cursor.execute("RELEASE SAVEPOINT audit_writer_update")

        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_worker")

        version_id = uuid.uuid4()
        cursor.execute(
            """
            INSERT INTO app.document_versions (id, document_id, version_number)
            VALUES (%s, %s, 1)
            """,
            (version_id, restricted_doc),
        )

        with pytest.raises(psycopg.errors.RaiseException, match="index rejected"):
            cursor.execute("SAVEPOINT restricted_graph_job")
            cursor.execute(
                """
                INSERT INTO app.lightrag_index_jobs (
                  document_id,
                  version_id,
                  operation,
                  idempotency_key
                )
                VALUES (%s, %s, 'index', %s)
                """,
                (restricted_doc, version_id, f"graph-{uuid.uuid4()}"),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT restricted_graph_job")
        cursor.execute("RELEASE SAVEPOINT restricted_graph_job")

        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_worker")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("SAVEPOINT worker_conversation_read")
            cursor.execute("SELECT 1 FROM app.conversations LIMIT 1")
        cursor.execute("ROLLBACK TO SAVEPOINT worker_conversation_read")
        cursor.execute("RELEASE SAVEPOINT worker_conversation_read")

        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_api")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("SAVEPOINT api_direct_write")
            cursor.execute(
                """
                INSERT INTO app.documents (title)
                VALUES ('direct write attempt')
                """
            )
        cursor.execute("ROLLBACK TO SAVEPOINT api_direct_write")
        cursor.execute("RELEASE SAVEPOINT api_direct_write")

        cursor.execute("SAVEPOINT api_direct_acl_write")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                """
                INSERT INTO app.document_acl (
                  document_id,
                  grantee_user_id
                )
                VALUES (%s, %s)
                """,
                (restricted_doc, user_b),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT api_direct_acl_write")
        cursor.execute("RELEASE SAVEPOINT api_direct_acl_write")

        cursor.execute("RESET ROLE")


def test_browser_roles_denied_direct_app_access(
    db_connection: psycopg.Connection,
) -> None:
    """Prove anon/authenticated cannot read canonical evidence tables directly."""

    with db_connection.cursor() as cursor:
        for role_name in ("anon", "authenticated"):
            cursor.execute(f"SET ROLE {role_name}")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute("SAVEPOINT browser_select")
                cursor.execute("SELECT 1 FROM app.documents LIMIT 1")
            cursor.execute("ROLLBACK TO SAVEPOINT browser_select")
            cursor.execute("RELEASE SAVEPOINT browser_select")
            cursor.execute("SAVEPOINT browser_acl_rpc")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(
                    """
                    SELECT private.set_document_acl(
                      NULL,
                      NULL,
                      NULL,
                      NULL,
                      NULL,
                      true
                    )
                    """
                )
            cursor.execute("ROLLBACK TO SAVEPOINT browser_acl_rpc")
            cursor.execute("RELEASE SAVEPOINT browser_acl_rpc")
            cursor.execute("RESET ROLE")


def test_visibility_change_bumps_authorization_and_bm25_job(
    db_connection: psycopg.Connection,
) -> None:
    """Prove visibility flips increment authorization_version and enqueue BM25 intent."""

    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, user_id, f"{user_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role)
            VALUES (%s, 'admin')
            """,
            (user_id,),
        )

        before_version = _auth_version(cursor)

        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility)
            VALUES (%s, 'Flip me', 'company_visible')
            """,
            (document_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (id, document_id, version_number)
            VALUES (%s, %s, 1)
            """,
            (version_id, document_id),
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
            UPDATE app.documents
            SET visibility = 'restricted'
            WHERE id = %s
            """,
            (document_id,),
        )

        after_version = _auth_version(cursor)
        assert after_version == before_version + 1

        cursor.execute(
            """
            SELECT count(*)
            FROM app.bm25_index_jobs
            WHERE payload_ref ->> 'document_id' = %s
              AND idempotency_key LIKE %s
            """,
            (str(document_id), "visibility:%"),
        )
        bm25_job_count = cursor.fetchone()
        assert bm25_job_count is not None
        assert bm25_job_count[0] >= 1

        cursor.execute(
            """
            SELECT visibility_generation
            FROM app.documents
            WHERE id = %s
            """,
            (document_id,),
        )
        generation = cursor.fetchone()
        assert generation is not None
        assert generation[0] >= 2


def test_full_role_acl_conversation_and_context_matrix(
    db_connection: psycopg.Connection,
) -> None:
    """Prove every v1 role, ACL mutation, privacy, and invalid context cell."""

    users = {
        "owner": uuid.uuid4(),
        "admin": uuid.uuid4(),
        "member": uuid.uuid4(),
        "upload_member": uuid.uuid4(),
        "viewer": uuid.uuid4(),
        "disabled": uuid.uuid4(),
    }
    company_document = uuid.uuid4()
    restricted_document = uuid.uuid4()
    member_conversation = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_profile(cursor, user_id=users["owner"], role="owner")
        _insert_profile(cursor, user_id=users["admin"], role="admin")
        _insert_profile(cursor, user_id=users["member"], role="member")
        _insert_profile(
            cursor,
            user_id=users["upload_member"],
            role="member",
            upload_enabled=True,
            mfa_enrolled=True,
        )
        _insert_profile(cursor, user_id=users["viewer"], role="viewer")
        _insert_profile(
            cursor,
            user_id=users["disabled"],
            role="member",
            disabled=True,
        )
        cursor.execute(
            """
            INSERT INTO app.documents (id, title, visibility, created_by)
            VALUES
              (%s, 'Company matrix document', 'company_visible', %s),
              (%s, 'Restricted matrix document', 'restricted', %s)
            """,
            (
                company_document,
                users["member"],
                restricted_document,
                users["member"],
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.conversations (id, creator_user_id, title)
            VALUES (%s, %s, 'Member private matrix thread')
            """,
            (member_conversation, users["member"]),
        )
        authorization_version = _auth_version(cursor)

        cursor.execute("SET ROLE app_api")

        authoritative_roles = {
            "owner": "owner",
            "admin": "admin",
            "member": "member",
            "upload_member": "member",
            "viewer": "viewer",
            "disabled": "member",
        }
        for name in authoritative_roles:
            _assert_fixture_document_visibility(
                _visible_document_ids(
                    cursor,
                    users[name],
                    authoritative_roles[name],
                    authorization_version,
                ),
                company_document=company_document,
                restricted_document=restricted_document,
                role_name=name,
            )

        assert member_conversation in _conversation_ids(
            cursor, users["member"], "member", authorization_version
        )
        assert member_conversation in _conversation_ids(
            cursor, users["owner"], "owner", authorization_version
        )
        assert member_conversation in _conversation_ids(
            cursor, users["admin"], "admin", authorization_version
        )
        assert member_conversation not in _conversation_ids(
            cursor, users["viewer"], "viewer", authorization_version
        )
        assert not _conversation_ids(
            cursor, users["disabled"], "member", authorization_version
        )

        assert not _visible_document_ids(cursor, None, "member", authorization_version)
        assert not _visible_document_ids(
            cursor, users["member"], None, authorization_version
        )
        assert not _visible_document_ids(cursor, users["member"], "member", None)
        assert not _visible_document_ids(
            cursor, uuid.uuid4(), "member", authorization_version
        )
        assert not _visible_document_ids(
            cursor, users["member"], "owner", authorization_version
        )
        assert not _visible_document_ids(
            cursor, users["member"], "member", authorization_version - 1
        )

        for name in ("member", "upload_member", "viewer", "disabled"):
            cursor.execute("SAVEPOINT denied_acl_mutation")
            with pytest.raises(psycopg.errors.RaiseException):
                _set_document_acl(
                    cursor,
                    caller_user_id=users[name],
                    caller_role=authoritative_roles[name],
                    authorization_version=authorization_version,
                    document_id=restricted_document,
                    grantee_user_id=users["viewer"],
                    grant=True,
                )
            cursor.execute("ROLLBACK TO SAVEPOINT denied_acl_mutation")
            cursor.execute("RELEASE SAVEPOINT denied_acl_mutation")

        assert _set_document_acl(
            cursor,
            caller_user_id=users["admin"],
            caller_role="admin",
            authorization_version=authorization_version,
            document_id=restricted_document,
            grantee_user_id=users["viewer"],
            grant=True,
        )
        granted_version = _auth_version(cursor)
        assert granted_version == authorization_version + 1
        assert restricted_document in _visible_document_ids(
            cursor, users["viewer"], "viewer", granted_version
        )

        assert not _set_document_acl(
            cursor,
            caller_user_id=users["admin"],
            caller_role="admin",
            authorization_version=granted_version,
            document_id=restricted_document,
            grantee_user_id=users["viewer"],
            grant=True,
        )
        assert _auth_version(cursor) == granted_version

        assert _set_document_acl(
            cursor,
            caller_user_id=users["owner"],
            caller_role="owner",
            authorization_version=granted_version,
            document_id=restricted_document,
            grantee_user_id=users["viewer"],
            grant=False,
        )
        revoked_version = _auth_version(cursor)
        assert revoked_version == granted_version + 1
        assert not _visible_document_ids(
            cursor, users["viewer"], "viewer", granted_version
        )
        assert restricted_document not in _visible_document_ids(
            cursor, users["viewer"], "viewer", revoked_version
        )

        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT event_type, actor_user_id, payload
            FROM app.audit_events
            WHERE target_id = %s
              AND event_type IN ('document_acl.granted', 'document_acl.revoked')
            ORDER BY chain_seq
            """,
            (restricted_document,),
        )
        acl_events = cursor.fetchall()
        assert [row[0] for row in acl_events] == [
            "document_acl.granted",
            "document_acl.revoked",
        ]
        assert acl_events[0][1] == users["admin"]
        assert acl_events[1][1] == users["owner"]
        assert all("raw_text" not in row[2] for row in acl_events)


def test_graph_downgrade_and_current_version_matrix(
    db_connection: psycopg.Connection,
) -> None:
    """Prove only current company-visible versions can enter graph indexing."""

    admin_user = uuid.uuid4()
    member_user = uuid.uuid4()
    document_id = uuid.uuid4()
    current_version = uuid.uuid4()
    old_version = uuid.uuid4()

    with db_connection.cursor() as cursor:
        _insert_profile(cursor, user_id=admin_user, role="admin")
        _insert_profile(cursor, user_id=member_user, role="member")
        cursor.execute(
            """
            INSERT INTO app.documents (
              id,
              title,
              visibility,
              graph_eligible,
              created_by
            )
            VALUES (%s, 'Graph matrix document', 'company_visible', false, %s)
            """,
            (document_id, member_user),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id,
              document_id,
              version_number
            )
            VALUES (%s, %s, 1), (%s, %s, 2)
            """,
            (old_version, document_id, current_version, document_id),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET current_version_id = %s,
                graph_eligible = true
            WHERE id = %s
            """,
            (current_version, document_id),
        )
        authorization_version = _auth_version(cursor)
        cursor.execute("SET ROLE app_api")

        cursor.execute(
            "SELECT app.assert_graph_index_allowed(%s, %s)",
            (document_id, current_version),
        )
        assert cursor.fetchone() == (True,)

        cursor.execute("SAVEPOINT non_current_graph")
        with pytest.raises(psycopg.errors.RaiseException, match="non-current"):
            cursor.execute(
                "SELECT app.assert_graph_index_allowed(%s, %s)",
                (document_id, old_version),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT non_current_graph")
        cursor.execute("RELEASE SAVEPOINT non_current_graph")

        cursor.execute("SAVEPOINT member_visibility")
        with pytest.raises(psycopg.errors.RaiseException, match="owner/admin"):
            cursor.execute(
                """
                SELECT app.set_document_visibility(
                  %s,
                  'member',
                  %s,
                  %s,
                  'restricted'::app.document_visibility
                )
                """,
                (member_user, authorization_version, document_id),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT member_visibility")
        cursor.execute("RELEASE SAVEPOINT member_visibility")

        cursor.execute(
            """
            SELECT (changed).visibility, (changed).graph_eligible
            FROM (
              SELECT app.set_document_visibility(
                %s,
                'admin',
                %s,
                %s,
                'restricted'::app.document_visibility
              ) AS changed
            ) AS result
            """,
            (admin_user, authorization_version, document_id),
        )
        assert cursor.fetchone() == ("restricted", False)
        restricted_version = _auth_version(cursor)
        assert restricted_version == authorization_version + 1

        cursor.execute("SAVEPOINT restricted_graph")
        with pytest.raises(psycopg.errors.RaiseException, match="restricted"):
            cursor.execute(
                "SELECT app.assert_graph_index_allowed(%s, %s)",
                (document_id, current_version),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT restricted_graph")
        cursor.execute("RELEASE SAVEPOINT restricted_graph")
        cursor.execute("RESET ROLE")

        cursor.execute(
            """
            SELECT operation, priority
            FROM app.lightrag_index_jobs
            WHERE document_id = %s
              AND operation = 'graph_acl_remove'
            """,
            (document_id,),
        )
        assert cursor.fetchone() == ("graph_acl_remove", "high")


def test_reused_connection_identity_is_bound_to_rpc_arguments() -> None:
    """Prove a stale session GUC cannot leak identity across transactions."""

    url = resolve_supabase_db_url()
    refuse_hosted_destructive_dsn(url)
    connection = try_connect(url)
    if connection is None:
        pytest.skip("Local Supabase fixture unreachable")

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    restricted_document = uuid.uuid4()
    company_document = uuid.uuid4()
    backend_pid: int | None = None

    try:
        with connection.cursor() as cursor:
            _insert_profile(cursor, user_id=user_a, role="member")
            _insert_profile(cursor, user_id=user_b, role="member")
            cursor.execute(
                """
                INSERT INTO app.documents (id, title, visibility, created_by)
                VALUES
                  (%s, 'Pool restricted', 'restricted', %s),
                  (%s, 'Pool company', 'company_visible', %s)
                """,
                (restricted_document, user_a, company_document, user_a),
            )
            cursor.execute(
                """
                INSERT INTO app.document_acl (
                  document_id,
                  grantee_user_id,
                  granted_by
                )
                VALUES (%s, %s, %s)
                """,
                (restricted_document, user_a, user_a),
            )
            authorization_version = _auth_version(cursor)
            cursor.execute("SELECT pg_backend_pid()")
            pid_row = cursor.fetchone()
            assert pid_row is not None
            backend_pid = int(pid_row[0])
            cursor.execute(
                "SELECT set_config('request.jwt.claims', %s, false)",
                (f'{{"sub":"{user_a}","role":"member"}}',),
            )
            cursor.execute("SET ROLE app_api")
            assert restricted_document in _visible_document_ids(
                cursor, user_a, "member", authorization_version
            )
            cursor.execute("RESET ROLE")
        connection.commit()

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_backend_pid(), current_setting(%s, true)",
                ("request.jwt.claims",),
            )
            reuse_row = cursor.fetchone()
            assert reuse_row is not None
            assert int(reuse_row[0]) == backend_pid
            assert str(user_a) in str(reuse_row[1])

            cursor.execute("SET ROLE app_api")
            user_b_documents = _visible_document_ids(
                cursor, user_b, "member", authorization_version
            )
            assert company_document in user_b_documents
            assert restricted_document not in user_b_documents
            assert not _visible_document_ids(cursor, None, None, authorization_version)
            cursor.execute("RESET ROLE")
        connection.commit()
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("RESET request.jwt.claims")
            cursor.execute(
                "DELETE FROM app.documents WHERE id IN (%s, %s)",
                (restricted_document, company_document),
            )
            cursor.execute(
                "DELETE FROM app.profiles WHERE user_id IN (%s, %s)",
                (user_a, user_b),
            )
            cursor.execute(
                "DELETE FROM auth.users WHERE id IN (%s, %s)",
                (user_a, user_b),
            )
        connection.commit()
        connection.close()


def test_runtime_roles_are_non_privileged_and_schema_isolated(
    db_connection: psycopg.Connection,
) -> None:
    """Prove runtime roles cannot bootstrap or cross private schema boundaries."""

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              rolname,
              rolsuper,
              rolcreaterole,
              rolcreatedb,
              rolcanlogin,
              rolbypassrls
            FROM pg_roles
            WHERE rolname LIKE 'app\\_%' ESCAPE '\\'
            ORDER BY rolname
            """
        )
        role_rows = cursor.fetchall()
        assert len(role_rows) == 5
        assert all(row[1:] == (False, False, False, False, False) for row in role_rows)

        for role_name in ("app_checkpointer", "app_lightrag"):
            if role_name == "app_checkpointer":
                cursor.execute("SET ROLE app_checkpointer")
                cursor.execute("SELECT count(*) FROM langgraph.checkpoints")
            else:
                cursor.execute("SET ROLE app_lightrag")
                cursor.execute("SELECT count(*) FROM lightrag.schema_capture_status")
            assert cursor.fetchone() is not None
            cursor.execute("SAVEPOINT denied_cross_schema")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute("SELECT 1 FROM app.documents LIMIT 1")
            cursor.execute("ROLLBACK TO SAVEPOINT denied_cross_schema")
            cursor.execute("RELEASE SAVEPOINT denied_cross_schema")
            cursor.execute("RESET ROLE")
