"""Contract tests for entity-rule CRUD, invalidation, and rebuild scheduling."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from smart_rag_core.jobs.entity_rule_service import (
    approve_entity_rule,
    list_entity_rules,
    revoke_entity_rule,
    suggest_entity_rule,
    upsert_entity_rule,
)
from smart_rag_core.jobs.entity_rules import EntityRuleDraft
from smart_rag_core.jobs.exceptions import GraphEntityRuleError
from smart_rag_core.jobs.graph_mapping_persist import load_entity_rules
from smart_rag_core.retrieval.graph import DEFAULT_GRAPH_WORKSPACE

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


def test_approved_rule_invalidates_maps_and_schedules_rebuild(
    db_connection: psycopg.Connection,
) -> None:
    """Approved rules bump generation, stamp maps stale, and isolate rebuild."""

    owner_id = uuid4()
    url = require_supabase_db_url()
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
        cursor.execute(
            """
            INSERT INTO app.lightrag_source_map (
              document_id, lightrag_workspace, lightrag_doc_id, workspace_key,
              pipeline_version, config_generation
            )
            SELECT
              d.id,
              %s,
              'doc-seed',
              %s,
              'graph_pipeline_v1',
              'live-config-seed'
            FROM app.documents AS d
            WHERE NOT EXISTS (
              SELECT 1
              FROM app.lightrag_source_map AS existing
              WHERE existing.document_id = d.id
            )
            LIMIT 1
            """,
            (DEFAULT_GRAPH_WORKSPACE, DEFAULT_GRAPH_WORKSPACE),
        )
        inserted_map = cursor.rowcount
        cursor.execute("SELECT count(*) FROM app.search_aliases")
        aliases_before = cursor.fetchone()
        db_connection.commit()
    suffix = uuid4().hex[:8]
    outcome = upsert_entity_rule(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        draft=EntityRuleDraft(
            entity_type="PROJECT",
            canonical_name=f"Atlas-{suffix}",
            aliases=(f"ATLAS-{suffix}",),
            reason="sme-curation",
            source="admin",
            status="approved",
        ),
    )
    assert outcome.status == "approved"
    assert outcome.invalidated is True
    assert outcome.rebuild_job_id is not None
    assert outcome.entity_rules_generation >= 2
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT config_generation
            FROM app.lightrag_source_map
            WHERE workspace_key = %s
              AND config_generation LIKE 'invalidated:%%'
            """,
            (DEFAULT_GRAPH_WORKSPACE,),
        )
        stale = cursor.fetchall()
        if inserted_map:
            assert stale
        cursor.execute(
            """
            SELECT workspace_key, state::text
            FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (f"{DEFAULT_GRAPH_WORKSPACE}__rebuild",),
        )
        rebuild = cursor.fetchone()
        assert rebuild is not None
        assert rebuild[1] == "building"
        cursor.execute(
            """
            SELECT operation::text, payload_ref ->> 'live_pointer_unchanged'
            FROM app.lightrag_index_jobs
            WHERE id = %s
            """,
            (outcome.rebuild_job_id,),
        )
        job = cursor.fetchone()
        assert job is not None
        assert job[0] == "rebuild"
        assert job[1] == "true"
        cursor.execute(
            """
            SELECT workspace_id
            FROM app.graph_active_workspace_pointer
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        pointer = cursor.fetchone()
        cursor.execute(
            """
            SELECT id FROM app.graph_workspaces WHERE workspace_key = %s
            """,
            (f"{DEFAULT_GRAPH_WORKSPACE}__rebuild",),
        )
        rebuild_id = cursor.fetchone()
        if pointer is not None and rebuild_id is not None:
            assert pointer[0] != rebuild_id[0] or pointer[0] is None
        cursor.execute("SELECT count(*) FROM app.search_aliases")
        aliases_after = cursor.fetchone()
        assert aliases_before is not None
        assert aliases_after is not None
        assert int(aliases_after[0]) == int(aliases_before[0])
        cursor.execute(
            """
            SELECT count(*)
            FROM app.audit_events
            WHERE event_type = 'graph.entity_rules.upserted'
              AND target_id = %s
            """,
            (outcome.rule_id,),
        )
        audited = cursor.fetchone()
        assert audited is not None
        assert int(audited[0]) >= 1
        views = load_entity_rules(db_connection)
        assert any(
            view.canonical_name == f"Atlas-{suffix}" and view.status == "approved"
            for view in views
        )


def test_suggestion_stays_inactive_until_explicit_approval(
    db_connection: psycopg.Connection,
) -> None:
    """Feedback suggestions do not load until approve; revoke of suggestion skips rebuild."""

    owner_id = uuid4()
    url = require_supabase_db_url()
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
        cursor.execute(
            """
            SELECT entity_rules_generation
            FROM app.graph_extraction_policy
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        before = cursor.fetchone()
        db_connection.commit()
    generation_before = int(before[0]) if before is not None else 1
    suffix = uuid4().hex[:8]
    suggested = suggest_entity_rule(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        draft=EntityRuleDraft(
            entity_type="PRODUCT",
            canonical_name=f"Nimbus-{suffix}",
            aliases=(f"NIM-{suffix}",),
            source="feedback",
            confidence=0.42,
            status="suggested",
        ),
    )
    assert suggested.status == "suggested"
    assert suggested.invalidated is False
    views = load_entity_rules(db_connection)
    assert all(view.canonical_name != f"Nimbus-{suffix}" for view in views)
    revoked = revoke_entity_rule(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        rule_id=suggested.rule_id,
        row_version=suggested.row_version,
    )
    assert revoked.status == "revoked"
    assert revoked.invalidated is False
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT entity_rules_generation
            FROM app.graph_extraction_policy
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
        after = cursor.fetchone()
    assert after is not None
    assert int(after[0]) == generation_before


def test_stale_update_and_member_are_rejected(
    db_connection: psycopg.Connection,
) -> None:
    """Optimistic concurrency and member mutations fail closed."""

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
    created = upsert_entity_rule(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        draft=EntityRuleDraft(
            entity_type="ORG",
            canonical_name=f"Acme-{suffix}",
            source="admin",
            status="approved",
        ),
    )
    with pytest.raises(GraphEntityRuleError, match="forbidden"):
        upsert_entity_rule(
            url,
            caller_user_id=member_id,
            caller_role="member",
            caller_authorization_version=auth_version,
            draft=EntityRuleDraft(
                entity_type="ORG",
                canonical_name=f"Nope-{suffix}",
                source="admin",
                status="approved",
            ),
        )
    with pytest.raises(GraphEntityRuleError, match="forbidden"):
        list_entity_rules(
            url,
            caller_user_id=member_id,
            caller_role="member",
            caller_authorization_version=auth_version,
        )
    with pytest.raises(GraphEntityRuleError, match="stale_row_version"):
        upsert_entity_rule(
            url,
            caller_user_id=owner_id,
            caller_role="owner",
            caller_authorization_version=auth_version,
            draft=EntityRuleDraft(
                entity_type="ORG",
                canonical_name=f"Acme-{suffix}-renamed",
                source="admin",
                status="approved",
            ),
            rule_id=created.rule_id,
            row_version=created.row_version - 1 if created.row_version > 1 else 0,
        )
    listed = list_entity_rules(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
    )
    assert any(item.id == created.rule_id for item in listed)


def test_approve_then_revoke_reloads_only_approved(
    db_connection: psycopg.Connection,
) -> None:
    """Approval loads the rule; revocation removes it from mapping views."""

    owner_id = uuid4()
    url = require_supabase_db_url()
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
        db_connection.commit()
    suffix = uuid4().hex[:8]
    suggested = suggest_entity_rule(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        draft=EntityRuleDraft(
            entity_type="LOCATION",
            canonical_name=f"Harbor-{suffix}",
            aliases=(f"HRB-{suffix}",),
            source="model",
            confidence=0.81,
            status="suggested",
        ),
    )
    approved = approve_entity_rule(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        rule_id=suggested.rule_id,
        row_version=suggested.row_version,
    )
    assert approved.invalidated is True
    views = load_entity_rules(db_connection)
    assert any(view.canonical_name == f"Harbor-{suffix}" for view in views)
    revoked = revoke_entity_rule(
        url,
        caller_user_id=owner_id,
        caller_role="owner",
        caller_authorization_version=auth_version,
        rule_id=approved.rule_id,
        row_version=approved.row_version,
    )
    assert revoked.invalidated is True
    views_after = load_entity_rules(db_connection)
    assert all(view.canonical_name != f"Harbor-{suffix}" for view in views_after)
