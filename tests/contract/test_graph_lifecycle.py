"""Contract tests for Packet 7 pointer switch, deletion/ACL, and upgrade isolation."""

from __future__ import annotations

# Jobs helpers must load before chunking.normalize to avoid a
# settings/jobs/retrieval import cycle. Keep this order.
# ruff: noqa: I001

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.jobs.exceptions import GraphLifecycleError
from smart_rag_core.jobs.graph_cleanup import (
    enqueue_surviving_rebuild,
    graph_maintenance_rebuild_funded,
    surviving_shared_entity_contamination,
    verify_application_residue,
)
from smart_rag_core.jobs.graph_pointer_switch import (
    disable_workspace,
    load_pointer_for_cas,
    switch_active_workspace,
    switch_document_version,
)
from smart_rag_core.jobs.limits import GRAPH_PIPELINE_VERSION, GRAPH_POINTER_ID
from smart_rag_core.retrieval.graph import (
    DEFAULT_GRAPH_WORKSPACE,
    GraphLimitationCode,
    workspace_limitation_code,
)
from smart_rag_core.ingestion.chunking.normalize import content_hash

from tests.contract.integration_support import (
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)


def _require_postgres() -> psycopg.Connection:
    """Open Postgres or skip when local Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail(
                "Graph lifecycle integration requires reachable Supabase Postgres"
            )
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    return connection


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one connection rolled back after each test."""

    connection = _require_postgres()
    yield connection
    connection.rollback()
    connection.close()


def _insert_auth_user(cursor: psycopg.Cursor, user_id: UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row."""

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


def _auth_version(cursor: psycopg.Cursor) -> int:
    """Return the live company authorization version."""

    cursor.execute("SELECT app.current_authorization_version()")
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _ensure_live_workspace(cursor: psycopg.Cursor) -> UUID:
    """Return ``company_default`` workspace id, creating it when missing."""

    cursor.execute(
        """
        INSERT INTO app.graph_workspaces (workspace_key, state)
        VALUES (%s, 'active'::app.graph_workspace_state)
        ON CONFLICT (workspace_key) DO UPDATE SET
          state = 'active'::app.graph_workspace_state
        RETURNING id
        """,
        (DEFAULT_GRAPH_WORKSPACE,),
    )
    row = cursor.fetchone()
    assert row is not None
    workspace_id = UUID(str(row[0]))
    cursor.execute(
        """
        UPDATE app.graph_active_workspace_pointer
        SET workspace_id = %s
        WHERE id = %s::uuid
        """,
        (workspace_id, GRAPH_POINTER_ID),
    )
    return workspace_id


def _seed_two_versions(
    cursor: psycopg.Cursor,
    *,
    owner_id: UUID,
) -> tuple[UUID, UUID, UUID]:
    """Insert one document with a current version and a pending replacement.

    Args:
        cursor: Open Postgres cursor as a privileged role.
        owner_id: Document creator.

    Returns:
        ``(document_id, old_version_id, new_version_id)``.
    """

    document_id = uuid4()
    old_version_id = uuid4()
    new_version_id = uuid4()
    old_chunk_id = uuid4()
    new_chunk_id = uuid4()
    old_text = "old canonical graph passage"
    new_text = "new canonical graph passage"
    cursor.execute(
        """
        INSERT INTO app.documents (id, title, visibility, created_by, graph_eligible)
        VALUES (%s, 'Switch Doc', 'company_visible', %s, false)
        """,
        (document_id, owner_id),
    )
    cursor.execute(
        """
        INSERT INTO app.document_versions (
          id, document_id, version_number, created_by, status, language,
          graph_eligible, hybrid_verified_at, content_hash, is_current
        )
        VALUES
          (
            %s, %s, 1, %s, 'graph_ready'::app.document_status, 'en',
            true, timezone('utc', now()), %s, true
          ),
          (
            %s, %s, 2, %s, 'graph_pending'::app.document_status, 'en',
            true, timezone('utc', now()), %s, false
          )
        """,
        (
            old_version_id,
            document_id,
            owner_id,
            content_hash(old_text),
            new_version_id,
            document_id,
            owner_id,
            content_hash(new_text),
        ),
    )
    cursor.execute(
        """
        UPDATE app.documents
        SET current_version_id = %s, graph_eligible = true
        WHERE id = %s
        """,
        (old_version_id, document_id),
    )
    cursor.execute(
        """
        INSERT INTO app.document_chunks (
          id, document_id, version_id, chunk_index, raw_text, content_hash
        )
        VALUES
          (%s, %s, %s, 0, %s, %s),
          (%s, %s, %s, 0, %s, %s)
        """,
        (
            old_chunk_id,
            document_id,
            old_version_id,
            old_text,
            content_hash(old_text),
            new_chunk_id,
            document_id,
            new_version_id,
            new_text,
            content_hash(new_text),
        ),
    )
    cursor.execute(
        """
        INSERT INTO app.lightrag_source_map (
          document_id, lightrag_workspace, lightrag_doc_id, version_id,
          workspace_key, pipeline_version, config_generation, retrieval_eligible
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'live-config', true)
        """,
        (
            document_id,
            DEFAULT_GRAPH_WORKSPACE,
            str(old_version_id),
            old_version_id,
            DEFAULT_GRAPH_WORKSPACE,
            GRAPH_PIPELINE_VERSION,
        ),
    )
    cursor.execute(
        """
        INSERT INTO app.lightrag_chunk_map (
          chunk_id, lightrag_doc_id, lightrag_chunk_id, version_id,
          workspace_key, pipeline_version, config_generation, support,
          retrieval_eligible
        )
        VALUES
          (%s, %s, 'old-chunk', %s, %s, %s, 'live-config', 0.91, true),
          (%s, %s, 'new-chunk', %s, %s, %s, 'live-config', 0.91, false)
        """,
        (
            old_chunk_id,
            str(old_version_id),
            old_version_id,
            DEFAULT_GRAPH_WORKSPACE,
            GRAPH_PIPELINE_VERSION,
            new_chunk_id,
            str(new_version_id),
            new_version_id,
            DEFAULT_GRAPH_WORKSPACE,
            GRAPH_PIPELINE_VERSION,
        ),
    )
    shared_entity = "ENTITY::shared"
    cursor.execute(
        """
        INSERT INTO app.graph_evidence_map (
          graph_object_type, graph_object_id, chunk_id, confidence,
          version_id, workspace_key, pipeline_version, config_generation,
          support, provenance, retrieval_eligible
        )
        VALUES
          (
            'entity', %s, %s, 0.91, %s, %s, %s, 'live-config', 0.91,
            jsonb_build_object('vendor_name', 'Shared'), true
          ),
          (
            'entity', %s, %s, 0.91, %s, %s, %s, 'live-config', 0.91,
            jsonb_build_object('vendor_name', 'Shared'), false
          )
        """,
        (
            shared_entity,
            old_chunk_id,
            old_version_id,
            DEFAULT_GRAPH_WORKSPACE,
            GRAPH_PIPELINE_VERSION,
            shared_entity,
            new_chunk_id,
            new_version_id,
            DEFAULT_GRAPH_WORKSPACE,
            GRAPH_PIPELINE_VERSION,
        ),
    )
    return document_id, old_version_id, new_version_id


def _seed_owner(cursor: psycopg.Cursor) -> UUID:
    """Insert one owner/admin profile and return the user id."""

    owner_id = uuid4()
    _insert_auth_user(cursor, owner_id, f"{owner_id}@example.com")
    cursor.execute(
        """
        INSERT INTO app.profiles (user_id, role, mfa_enrolled)
        VALUES (%s, 'admin', true)
        """,
        (owner_id,),
    )
    return owner_id


def test_version_switch_exposes_exactly_one_current(
    db_connection: psycopg.Connection,
) -> None:
    """Commit flips one current version and filters the superseded maps."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        owner_id = _seed_owner(cursor)
        _ensure_live_workspace(cursor)
        document_id, old_id, new_id = _seed_two_versions(cursor, owner_id=owner_id)
    generation, _workspace = load_pointer_for_cas(db_connection)
    result = switch_document_version(
        db_connection,
        document_id=document_id,
        new_version_id=new_id,
        old_version_id=old_id,
        expected_generation=generation,
        expected_workspace_key=DEFAULT_GRAPH_WORKSPACE,
    )
    assert result.switched is True
    assert result.generation == generation
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_version_id FROM app.documents WHERE id = %s",
            (document_id,),
        )
        current = cursor.fetchone()
        cursor.execute(
            """
            SELECT id FROM app.document_versions
            WHERE document_id = %s AND is_current = true
            """,
            (document_id,),
        )
        current_flags = cursor.fetchall()
        cursor.execute(
            """
            SELECT retrieval_eligible FROM app.lightrag_chunk_map
            WHERE version_id = %s
            """,
            (old_id,),
        )
        old_map = cursor.fetchone()
        cursor.execute(
            """
            SELECT retrieval_eligible FROM app.lightrag_chunk_map
            WHERE version_id = %s
            """,
            (new_id,),
        )
        new_map = cursor.fetchone()
        cursor.execute(
            """
            SELECT target_cleanup_at, clean_rebuild_at, reason
            FROM app.graph_cleanup_tombstones
            WHERE version_id = %s
            """,
            (old_id,),
        )
        tombstone = cursor.fetchone()
        cursor.execute(
            """
            SELECT version_id, retrieval_eligible
            FROM app.lightrag_source_map
            WHERE document_id = %s
            """,
            (document_id,),
        )
        source_map = cursor.fetchone()
    assert current is not None
    assert UUID(str(current[0])) == new_id
    assert len(current_flags) == 1
    assert UUID(str(current_flags[0][0])) == new_id
    assert old_map is not None and old_map[0] is False
    assert new_map is not None and new_map[0] is True
    assert source_map is not None
    assert UUID(str(source_map[0])) == new_id
    assert source_map[1] is True
    assert tombstone is not None
    assert tombstone[2] == "version_supersede"
    now = datetime.now(tz=UTC)
    assert timedelta(hours=23) < (tombstone[0] - now) < timedelta(hours=25)
    assert timedelta(days=6) < (tombstone[1] - now) < timedelta(days=8)


def test_stale_generation_savepoint_keeps_old_current(
    db_connection: psycopg.Connection,
) -> None:
    """Failed CAS inside a savepoint leaves exactly one old current version."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        owner_id = _seed_owner(cursor)
        _ensure_live_workspace(cursor)
        document_id, old_id, new_id = _seed_two_versions(cursor, owner_id=owner_id)
        generation, _workspace = load_pointer_for_cas(db_connection)
        cursor.execute("SAVEPOINT switch_cas")
        with pytest.raises(psycopg.errors.RaiseException, match="stale_generation"):
            cursor.execute(
                """
                SELECT app.switch_graph_document_version(%s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    new_id,
                    old_id,
                    generation + 9,
                    DEFAULT_GRAPH_WORKSPACE,
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT switch_cas")
        cursor.execute(
            "SELECT current_version_id FROM app.documents WHERE id = %s",
            (document_id,),
        )
        current = cursor.fetchone()
        cursor.execute(
            """
            SELECT count(*) FROM app.document_versions
            WHERE document_id = %s AND is_current = true
            """,
            (document_id,),
        )
        flags = cursor.fetchone()
    assert current is not None
    assert UUID(str(current[0])) == old_id
    assert flags is not None
    assert int(flags[0]) == 1


def test_canonical_exclusion_filters_maps_immediately(
    db_connection: psycopg.Connection,
) -> None:
    """Phase 3 exclusion marks maps ineligible before vendor mutation."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        owner_id = _seed_owner(cursor)
        _ensure_live_workspace(cursor)
        _document_id, old_id, _new_id = _seed_two_versions(cursor, owner_id=owner_id)
        cursor.execute(
            """
            UPDATE app.document_versions
            SET retrieval_eligible = false
            WHERE id = %s
            """,
            (old_id,),
        )
        cursor.execute(
            """
            SELECT retrieval_eligible FROM app.lightrag_chunk_map
            WHERE version_id = %s
            """,
            (old_id,),
        )
        chunk_flag = cursor.fetchone()
        cursor.execute(
            """
            SELECT retrieval_eligible FROM app.graph_evidence_map
            WHERE version_id = %s
            """,
            (old_id,),
        )
        evidence_flag = cursor.fetchone()
    assert chunk_flag is not None and chunk_flag[0] is False
    assert evidence_flag is not None and evidence_flag[0] is False
    residue = verify_application_residue(
        db_connection,
        version_id=old_id,
        workspace_key=DEFAULT_GRAPH_WORKSPACE,
    )
    assert residue.clean is True


def test_shared_entity_deleted_version_does_not_survive(
    db_connection: psycopg.Connection,
) -> None:
    """Shared entities keep surviving sources; deleted versions are filtered."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        owner_id = _seed_owner(cursor)
        _ensure_live_workspace(cursor)
        _document_id, old_id, new_id = _seed_two_versions(cursor, owner_id=owner_id)
        cursor.execute(
            """
            UPDATE app.document_versions
            SET retrieval_eligible = false
            WHERE id = %s
            """,
            (old_id,),
        )
        cursor.execute(
            """
            UPDATE app.lightrag_chunk_map
            SET retrieval_eligible = true
            WHERE version_id = %s
            """,
            (new_id,),
        )
        cursor.execute(
            """
            UPDATE app.graph_evidence_map
            SET retrieval_eligible = true
            WHERE version_id = %s
            """,
            (new_id,),
        )
    assert (
        surviving_shared_entity_contamination(
            db_connection,
            deleted_version_id=old_id,
            workspace_key=DEFAULT_GRAPH_WORKSPACE,
        )
        is False
    )
    survivor = verify_application_residue(
        db_connection,
        version_id=new_id,
        workspace_key=DEFAULT_GRAPH_WORKSPACE,
    )
    assert survivor.clean is False


def test_acl_expansion_never_auto_indexes(
    db_connection: psycopg.Connection,
) -> None:
    """Restricted to company_visible does not enqueue a graph index job."""

    owner_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        _insert_auth_user(cursor, owner_id, f"{owner_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, mfa_enrolled)
            VALUES (%s, 'owner', true)
            """,
            (owner_id,),
        )
        cursor.execute(
            """
            INSERT INTO app.documents (
              id, title, visibility, created_by, graph_eligible
            )
            VALUES (%s, 'ACL Expand', 'restricted', %s, false)
            """,
            (document_id, owner_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, created_by, status
            )
            VALUES (%s, %s, 1, %s, 'hybrid_ready'::app.document_status)
            """,
            (version_id, document_id, owner_id),
        )
        cursor.execute(
            "UPDATE app.documents SET current_version_id = %s WHERE id = %s",
            (version_id, document_id),
        )
        auth_version = _auth_version(cursor)
        cursor.execute(
            """
            SELECT app.set_document_visibility(
              %s, 'owner', %s, %s, 'company_visible'
            )
            """,
            (owner_id, auth_version, document_id),
        )
        cursor.execute(
            """
            SELECT count(*) FROM app.lightrag_index_jobs
            WHERE document_id = %s AND operation = 'index'
            """,
            (document_id,),
        )
        after_index = cursor.fetchone()
        cursor.execute(
            """
            SELECT count(*) FROM app.lightrag_index_jobs
            WHERE document_id = %s AND operation = 'graph_acl_remove'
            """,
            (document_id,),
        )
        acl_remove = cursor.fetchone()
    assert after_index is not None and int(after_index[0]) == 0
    assert acl_remove is not None and int(acl_remove[0]) == 0


def test_same_schema_upgrade_is_recorded_as_refused(
    db_connection: psycopg.Connection,
) -> None:
    """A second workspace in runtime lightrag is not upgrade proof."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT app.record_graph_upgrade_qualification(
              'postgres', 'lightrag', 'postgres', 'lightrag', 'recorded', ''
            )
            """
        )
        row = cursor.fetchone()
        assert row is not None
        cursor.execute(
            """
            SELECT status FROM app.graph_upgrade_qualifications WHERE id = %s
            """,
            (row[0],),
        )
        detail = cursor.fetchone()
        cursor.execute(
            """
            SELECT app.record_graph_upgrade_qualification(
              'lightrag_upgrade_copy', 'lightrag', 'postgres', 'lightrag',
              'passed', 'isolated copy'
            )
            """
        )
        isolated = cursor.fetchone()
    assert detail is not None
    assert str(detail[0]) == "refused_same_schema"
    assert isolated is not None


def test_disable_workspace_emits_outage_signal(
    db_connection: psycopg.Connection,
) -> None:
    """Disabled workspaces are not queryable."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        _ensure_live_workspace(cursor)
    workspace_id = disable_workspace(
        db_connection,
        workspace_key=DEFAULT_GRAPH_WORKSPACE,
        reason="upgrade_qualification_failed",
    )
    assert workspace_id is not None
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT state::text FROM app.graph_workspaces
            WHERE workspace_key = %s
            """,
            (DEFAULT_GRAPH_WORKSPACE,),
        )
        row = cursor.fetchone()
    assert row is not None
    assert (
        workspace_limitation_code(str(row[0]), pointer_attached=True)
        is GraphLimitationCode.GRAPH_OUTAGE
    )


def test_unfunded_rebuild_fails_closed(
    db_connection: psycopg.Connection,
) -> None:
    """Exhausted maintenance reserve refuses the surviving rebuild enqueue."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.company_settings
            SET monthly_graph_maintenance_budget_usd = 0
            WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
            """
        )
    assert graph_maintenance_rebuild_funded(db_connection) is False
    with pytest.raises(GraphLifecycleError, match="unfunded_rebuild"):
        enqueue_surviving_rebuild(
            db_connection,
            workspace_key=DEFAULT_GRAPH_WORKSPACE,
            funded=False,
        )


def test_workspace_switch_bumps_generation(
    db_connection: psycopg.Connection,
) -> None:
    """Verified rebuild switch attaches exactly one workspace and bumps generation."""

    rebuild_key = f"{DEFAULT_GRAPH_WORKSPACE}__rebuild"
    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        live_id = _ensure_live_workspace(cursor)
        cursor.execute(
            """
            INSERT INTO app.graph_workspaces (workspace_key, state)
            VALUES (%s, 'building'::app.graph_workspace_state)
            ON CONFLICT (workspace_key) DO UPDATE SET
              state = 'building'::app.graph_workspace_state
            RETURNING id
            """,
            (rebuild_key,),
        )
        target_row = cursor.fetchone()
        assert target_row is not None
        target_id = UUID(str(target_row[0]))
    generation, _workspace = load_pointer_for_cas(db_connection)
    result = switch_active_workspace(
        db_connection,
        expected_generation=generation,
        expected_workspace_key=DEFAULT_GRAPH_WORKSPACE,
        target_workspace_key=rebuild_key,
        target_embedding_model="text-embedding-3-large",
        target_embedding_dimensions=1024,
        source_embedding_model="text-embedding-3-large",
        source_embedding_dimensions=1024,
    )
    assert result.new_generation == generation + 1
    assert result.new_workspace_id == target_id
    assert result.old_workspace_id == live_id
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT workspace_id, generation
            FROM app.graph_active_workspace_pointer
            WHERE id = %s::uuid
            """,
            (GRAPH_POINTER_ID,),
        )
        pointer = cursor.fetchone()
        cursor.execute(
            "SELECT state::text FROM app.graph_workspaces WHERE id = %s",
            (live_id,),
        )
        old_state = cursor.fetchone()
        cursor.execute(
            "SELECT state::text FROM app.graph_workspaces WHERE id = %s",
            (target_id,),
        )
        new_state = cursor.fetchone()
    assert pointer is not None
    assert UUID(str(pointer[0])) == target_id
    assert int(pointer[1]) == generation + 1
    assert old_state is not None and old_state[0] == "retired"
    assert new_state is not None and new_state[0] == "active"


def test_build_index_allows_non_current_graph_eligible(
    db_connection: psycopg.Connection,
) -> None:
    """Pending-switch versions may index into a build workspace."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        owner_id = _seed_owner(cursor)
        document_id, _old_id, new_id = _seed_two_versions(cursor, owner_id=owner_id)
        cursor.execute("SAVEPOINT live_gate")
        with pytest.raises(psycopg.errors.RaiseException):
            cursor.execute(
                "SELECT app.assert_graph_index_allowed(%s, %s)",
                (document_id, new_id),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT live_gate")
        cursor.execute(
            "SELECT app.assert_graph_build_index_allowed(%s, %s)",
            (document_id, new_id),
        )
        allowed = cursor.fetchone()
        cursor.execute(
            """
            INSERT INTO app.lightrag_index_jobs (
              document_id, version_id, operation, idempotency_key, payload_ref
            )
            VALUES (%s, %s, 'index', %s, '{}'::jsonb)
            RETURNING id
            """,
            (document_id, new_id, f"pending-switch-index:{new_id}"),
        )
        job = cursor.fetchone()
    assert allowed is not None and allowed[0] is True
    assert job is not None


def test_in_place_embedding_mix_is_rejected_by_check(
    db_connection: psycopg.Connection,
) -> None:
    """Workspace embedding pins refuse mixed in-place configs."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        _ensure_live_workspace(cursor)
        cursor.execute("SAVEPOINT mix_embeddings")
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                """
                UPDATE app.graph_workspaces
                SET embedding_dimensions = 1536
                WHERE workspace_key = %s
                """,
                (DEFAULT_GRAPH_WORKSPACE,),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT mix_embeddings")
