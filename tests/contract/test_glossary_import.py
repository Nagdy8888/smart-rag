"""Contract tests for owner/admin glossary import, approval, and rollback."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.glossary.import_service import (
    GlossaryImportRejectedError,
    approve_glossary_import,
    import_glossary_batch,
    rollback_glossary_import,
)
from smart_rag_core.glossary.models import (
    GlossaryAliasDraft,
    GlossaryBatch,
    GlossaryEntryDraft,
    GlossaryEntryType,
    GlossaryImportStatus,
    GlossaryLanguage,
    GlossaryScope,
)
from smart_rag_core.glossary.validation import GlossaryValidationError
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

from tests.contract.integration_support import require_supabase_db_url, try_connect


def _insert_auth_user(cursor: psycopg.Cursor, user_id: object, email: str) -> None:
    """Insert one minimal auth user.

    Args:
        cursor: Open Postgres cursor.
        user_id: Auth user UUID.
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


def _auth_version(cursor: psycopg.Cursor) -> int:
    """Return live authorization version.

    Args:
        cursor: Open Postgres cursor.

    Returns:
        Company authorization snapshot.
    """

    cursor.execute("SELECT app.current_authorization_version()")
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _batch(suffix: str) -> GlossaryBatch:
    """Return a unique synthetic glossary batch.

    Args:
        suffix: Distinguishing suffix for keys.

    Returns:
        Valid glossary batch.
    """

    return GlossaryBatch(
        source_name="synthetic-seed",
        source_version="v1",
        idempotency_key=f"glossary-contract-{suffix}",
        entries=[
            GlossaryEntryDraft(
                entry_key=f"inv-{suffix}",
                canonical_term=f"INV-SR-{suffix[-4:].rjust(4, '8')}",
                language=GlossaryLanguage.EN,
                entry_type=GlossaryEntryType.PRODUCT_CODE,
                effective_scope=GlossaryScope.SYNTHETIC_EVAL,
                aliases=[
                    GlossaryAliasDraft(
                        alias=f"invoice {suffix}",
                        language=GlossaryLanguage.EN,
                    )
                ],
            )
        ],
    )


def test_owner_import_approve_projects_aliases_and_rollback_removes_them(
    db_connection: psycopg.Connection,
) -> None:
    """Approved aliases populate search_aliases; rollback deletes the projection."""

    owner_id = uuid4()
    member_id = uuid4()
    url = require_supabase_db_url()
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, owner_id, f"{owner_id}@example.com")
        _insert_auth_user(cursor, member_id, f"{member_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'owner', true, true), (%s, 'member', true, true)
            """,
            (owner_id, member_id),
        )
        auth_version = _auth_version(cursor)
        db_connection.commit()
    suffix = uuid4().hex[:8]
    batch = _batch(suffix)
    pending = import_glossary_batch(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        batch=batch,
    )
    assert pending.status is GlossaryImportStatus.PENDING_APPROVAL
    alias_norm = normalize_arabic_v1(f"invoice {suffix}")
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM app.search_aliases WHERE alias_normalized = %s",
            (alias_norm,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert int(row[0]) == 0
    approved = approve_glossary_import(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        import_id=pending.import_id,
    )
    assert approved.status is GlossaryImportStatus.APPROVED
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT canonical_term, import_id
            FROM app.search_aliases
            WHERE alias_normalized = %s
            """,
            (alias_norm,),
        )
        projected = cursor.fetchone()
        assert projected is not None
        assert str(projected[1]) == str(pending.import_id)
        cursor.execute(
            """
            SELECT payload
            FROM app.audit_events
            WHERE target_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (pending.import_id,),
        )
        audit = cursor.fetchone()
        assert audit is not None
        payload = audit[0]
        assert "invoice" not in str(payload)
        assert "INV-SR" not in str(payload)
    rolled = rollback_glossary_import(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        import_id=pending.import_id,
    )
    assert rolled.status is GlossaryImportStatus.ROLLED_BACK
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM app.search_aliases WHERE alias_normalized = %s",
            (alias_norm,),
        )
        remaining = cursor.fetchone()
        assert remaining is not None
        assert int(remaining[0]) == 0


def test_member_glossary_import_is_forbidden(db_connection: psycopg.Connection) -> None:
    """Members cannot import glossary rows through the RPC."""

    member_id = uuid4()
    url = require_supabase_db_url()
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, member_id, f"{member_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'member', true, true)
            """,
            (member_id,),
        )
        auth_version = _auth_version(cursor)
        db_connection.commit()
    with pytest.raises(GlossaryImportRejectedError, match="forbidden"):
        import_glossary_batch(
            url,
            caller_user_id=member_id,
            caller_role="member",
            caller_authorization_version=auth_version,
            batch=_batch(uuid4().hex[:8]),
        )


def test_sql_cycle_payload_is_rejected(db_connection: psycopg.Connection) -> None:
    """The SQL cycle detector rejects mutual aliases without Python pre-check."""

    owner_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, owner_id, f"{owner_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, upload_enabled, mfa_enrolled)
            VALUES (%s, 'owner', true, true)
            """,
            (owner_id,),
        )
        auth_version = _auth_version(cursor)
        cursor.execute("SET ROLE app_api")
        with pytest.raises(psycopg.Error, match="alias_cycle"):
            cursor.execute(
                """
                SELECT *
                FROM app.import_glossary_batch(
                  %s::uuid,
                  'owner'::text,
                  %s::bigint,
                  'cycle'::text,
                  'v1'::text,
                  %s::text,
                  %s::jsonb
                )
                """,
                (
                    owner_id,
                    auth_version,
                    f"glossary-sql-cycle-{uuid4().hex[:8]}",
                    """
                    {"entries":[
                      {"entry_key":"a","canonical_term":"alpha-term",
                       "language":"en","entry_type":"canonical_term",
                       "effective_scope":"synthetic_eval",
                       "aliases":[{"alias":"beta-term","language":"en"}]},
                      {"entry_key":"b","canonical_term":"beta-term",
                       "language":"en","entry_type":"canonical_term",
                       "effective_scope":"synthetic_eval",
                       "aliases":[{"alias":"alpha-term","language":"en"}]}
                    ]}
                    """,
                ),
            )


def test_unapproved_identifier_rule_rejected_before_rpc() -> None:
    """High-collision identifier rules never reach SQL."""

    batch = GlossaryBatch(
        source_name="bad-rule",
        source_version="v1",
        idempotency_key="glossary-bad-rule-0001",
        entries=[
            GlossaryEntryDraft(
                entry_key="digits",
                canonical_term="digit-rule",
                language=GlossaryLanguage.EN,
                entry_type=GlossaryEntryType.IDENTIFIER_RULE,
                effective_scope=GlossaryScope.SYNTHETIC_EVAL,
                identifier_pattern=r"\d{1,3}",
                aliases=[
                    GlossaryAliasDraft(alias="digits", language=GlossaryLanguage.EN)
                ],
            )
        ],
    )
    with pytest.raises(GlossaryValidationError, match="high_collision_rule"):
        from smart_rag_core.glossary.validation import validate_glossary_batch

        validate_glossary_batch(batch)
