"""Contract tests for Packet 5 resolver, inspection, ACL, and repair."""

from __future__ import annotations

# Resolver must load before chunking.normalize to avoid a
# settings/jobs/retrieval import cycle. Keep this order.
# ruff: noqa: I001

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.jobs.graph_resolver import (
    enqueue_query_repairs,
    inspect_graph,
    load_query_workspace,
    resolve_graph_leads,
    visibility_counts,
)
from smart_rag_core.ingestion.chunking.normalize import content_hash
from smart_rag_core.jobs.entity_rule_service import load_extraction_policy
from smart_rag_core.jobs.limits import GRAPH_POINTER_ID, GRAPH_QUERY_REPAIR_MAP_KIND
from smart_rag_core.retrieval.graph import (
    GraphLeadEntity,
    GraphLeadRelation,
    GraphLeadSet,
    graph_chunker_config_snapshot,
)
from smart_rag_core.retrieval.graph_mapping import mapping_config_generation
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.contract.integration_support import (
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)


@dataclass(frozen=True, slots=True)
class _GraphQuerySeed:
    """IDs for one Packet 5 resolver fixture."""

    member: CallerContext
    stranger: CallerContext
    workspace_key: str
    config_generation: str
    ready_document_id: UUID
    ready_version_id: UUID
    ready_chunk_id: UUID
    pending_version_id: UUID
    secret_document_id: UUID
    ineligible_version_id: UUID
    entity_alpha: str
    entity_beta: str
    statement_id: str
    vendor_chunk_id: str


def _require_postgres() -> psycopg.Connection:
    """Open Postgres or skip when local Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Graph resolver tests require reachable Supabase Postgres")
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    return connection


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield one connection. Tests commit fixtures and clean up."""

    connection = _require_postgres()
    yield connection
    connection.rollback()
    connection.close()


def _insert_auth_user(cursor: psycopg.Cursor, user_id: UUID, email: str) -> None:
    """Insert one minimal ``auth.users`` row.

    Args:
        cursor: Open cursor.
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


def _auth_version(cursor: psycopg.Cursor) -> int:
    """Return the live company authorization version.

    Args:
        cursor: Open cursor.

    Returns:
        Authorization version.
    """

    cursor.execute(
        """
        SELECT authorization_version
        FROM app.company_settings
        WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
        """
    )
    row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _seed(connection: psycopg.Connection) -> tuple[_GraphQuerySeed, object, object]:
    """Insert committed resolver fixtures and return restore tokens.

    Args:
        connection: Superuser connection.

    Returns:
        Seed, original pointer workspace id, original generation.
    """

    owner_id = uuid4()
    member_id = uuid4()
    stranger_id = uuid4()
    workspace_id = uuid4()
    workspace_key = f"p5-{uuid4().hex[:12]}"
    ready_document_id = uuid4()
    ready_version_id = uuid4()
    ready_chunk_id = uuid4()
    pending_document_id = uuid4()
    pending_version_id = uuid4()
    secret_document_id = uuid4()
    secret_version_id = uuid4()
    secret_chunk_id = uuid4()
    ineligible_document_id = uuid4()
    ineligible_version_id = uuid4()
    ineligible_chunk_id = uuid4()
    entity_alpha = "ent-alpha"
    entity_beta = "ent-beta"
    statement_id = "stmt-ab"
    vendor_chunk_id = "vendor-chunk-alpha"
    passage = "canonical graph resolver passage"
    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT workspace_id, generation
            FROM app.graph_active_workspace_pointer
            WHERE id = %s::uuid
            """,
            (GRAPH_POINTER_ID,),
        )
        pointer = cursor.fetchone()
        original_workspace = pointer[0] if pointer else None
        original_generation = int(pointer[1]) if pointer else 1
        _insert_auth_user(cursor, owner_id, f"{owner_id}@example.com")
        _insert_auth_user(cursor, member_id, f"{member_id}@example.com")
        _insert_auth_user(cursor, stranger_id, f"{stranger_id}@example.com")
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, mfa_enrolled)
            VALUES (%s, 'admin', true), (%s, 'member', true), (%s, 'member', true)
            """,
            (owner_id, member_id, stranger_id),
        )
        cursor.execute(
            """
            INSERT INTO app.graph_workspaces (id, workspace_key, state)
            VALUES (%s, %s, 'active')
            """,
            (workspace_id, workspace_key),
        )
        cursor.execute(
            """
            UPDATE app.graph_active_workspace_pointer
            SET workspace_id = %s, generation = 1
            WHERE id = %s::uuid
            """,
            (workspace_id, GRAPH_POINTER_ID),
        )
        policy = load_extraction_policy(connection)
        config_generation = mapping_config_generation(
            workspace_key=workspace_key,
            pointer_generation=1,
            chunker_snapshot=graph_chunker_config_snapshot(),
            entity_rules_generation=policy.entity_rules_generation,
            extraction_policy_hash=policy.extraction_policy_hash,
        )
        cursor.execute(
            """
            INSERT INTO app.documents (
              id, title, visibility, created_by, graph_eligible
            )
            VALUES
              (%s, 'Ready Graph Doc', 'company_visible', %s, false),
              (%s, 'Pending Hybrid Doc', 'company_visible', %s, false),
              (%s, 'Secret Graph Doc', 'restricted', %s, false),
              (%s, 'Ineligible Restricted', 'restricted', %s, false)
            """,
            (
                ready_document_id,
                owner_id,
                pending_document_id,
                owner_id,
                secret_document_id,
                owner_id,
                ineligible_document_id,
                owner_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.document_versions (
              id, document_id, version_number, created_by, status, language,
              graph_eligible, content_hash
            )
            VALUES
              (%s, %s, 1, %s, 'graph_ready', 'en', true, %s),
              (%s, %s, 1, %s, 'graph_pending', 'en', true, %s),
              (%s, %s, 1, %s, 'graph_ready', 'en', true, %s),
              (%s, %s, 1, %s, 'graph_ineligible', 'en', false, %s)
            """,
            (
                ready_version_id,
                ready_document_id,
                owner_id,
                content_hash(passage),
                pending_version_id,
                pending_document_id,
                owner_id,
                content_hash("pending"),
                secret_version_id,
                secret_document_id,
                owner_id,
                content_hash("secret"),
                ineligible_version_id,
                ineligible_document_id,
                owner_id,
                content_hash("ineligible"),
            ),
        )
        cursor.execute(
            """
            UPDATE app.documents SET current_version_id = %s WHERE id = %s
            """,
            (ready_version_id, ready_document_id),
        )
        cursor.execute(
            """
            UPDATE app.documents SET current_version_id = %s WHERE id = %s
            """,
            (pending_version_id, pending_document_id),
        )
        cursor.execute(
            """
            UPDATE app.documents SET current_version_id = %s WHERE id = %s
            """,
            (secret_version_id, secret_document_id),
        )
        cursor.execute(
            """
            UPDATE app.documents SET current_version_id = %s WHERE id = %s
            """,
            (ineligible_version_id, ineligible_document_id),
        )
        cursor.execute(
            """
            UPDATE app.documents
            SET graph_eligible = true
            WHERE id IN (%s, %s)
            """,
            (ready_document_id, pending_document_id),
        )
        cursor.execute(
            """
            INSERT INTO app.document_chunks (
              id, document_id, version_id, chunk_index, raw_text, content_hash,
              page_number
            )
            VALUES
              (%s, %s, %s, 0, %s, %s, 1),
              (%s, %s, %s, 0, 'secret', %s, 1),
              (%s, %s, %s, 0, 'ineligible', %s, 1)
            """,
            (
                ready_chunk_id,
                ready_document_id,
                ready_version_id,
                passage,
                content_hash(passage),
                secret_chunk_id,
                secret_document_id,
                secret_version_id,
                content_hash("secret"),
                ineligible_chunk_id,
                ineligible_document_id,
                ineligible_version_id,
                content_hash("ineligible"),
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.document_acl (
              document_id, grantee_user_id, granted_by
            )
            VALUES (%s, %s, %s), (%s, %s, %s)
            """,
            (
                secret_document_id,
                member_id,
                owner_id,
                ineligible_document_id,
                member_id,
                owner_id,
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.lightrag_chunk_map (
              chunk_id, lightrag_doc_id, lightrag_chunk_id, version_id,
              workspace_key, pipeline_version, config_generation, support
            )
            VALUES (%s, %s, %s, %s, %s, 'graph_pipeline_v1', %s, 0.91)
            """,
            (
                ready_chunk_id,
                str(ready_version_id),
                vendor_chunk_id,
                ready_version_id,
                workspace_key,
                config_generation,
            ),
        )
        cursor.execute(
            """
            INSERT INTO app.graph_evidence_map (
              graph_object_type, graph_object_id, chunk_id, confidence,
              version_id, workspace_key, pipeline_version, config_generation,
              support, provenance
            )
            VALUES
              (
                'entity', %s, %s, 0.91, %s, %s, 'graph_pipeline_v1', %s, 0.91,
                jsonb_build_object('vendor_name', 'Alpha')
              ),
              (
                'entity', %s, %s, 0.91, %s, %s, 'graph_pipeline_v1', %s, 0.91,
                jsonb_build_object('vendor_name', 'Beta')
              ),
              (
                'statement', %s, %s, 0.91, %s, %s, 'graph_pipeline_v1', %s, 0.91,
                jsonb_build_object('src', 'Alpha', 'tgt', 'Beta')
              ),
              (
                'path_edge', %s, %s, 0.91, %s, %s, 'graph_pipeline_v1', %s, 0.91,
                jsonb_build_object('statement_id', %s::text)
              ),
              (
                'entity', %s, %s, 0.91, %s, %s, 'graph_pipeline_v1', %s, 0.91,
                jsonb_build_object('vendor_name', 'SecretOrg')
              )
            """,
            (
                entity_alpha,
                ready_chunk_id,
                ready_version_id,
                workspace_key,
                config_generation,
                entity_beta,
                ready_chunk_id,
                ready_version_id,
                workspace_key,
                config_generation,
                statement_id,
                ready_chunk_id,
                ready_version_id,
                workspace_key,
                config_generation,
                "path-ab",
                ready_chunk_id,
                ready_version_id,
                workspace_key,
                config_generation,
                statement_id,
                "ent-secret",
                secret_chunk_id,
                secret_version_id,
                workspace_key,
                config_generation,
            ),
        )
        auth_version = _auth_version(cursor)
    connection.commit()
    member = CallerContext(
        user_id=str(member_id),
        role=UserRole.MEMBER,
        authorization_version=auth_version,
    )
    stranger = CallerContext(
        user_id=str(stranger_id),
        role=UserRole.MEMBER,
        authorization_version=auth_version,
    )
    seed = _GraphQuerySeed(
        member=member,
        stranger=stranger,
        workspace_key=workspace_key,
        config_generation=config_generation,
        ready_document_id=ready_document_id,
        ready_version_id=ready_version_id,
        ready_chunk_id=ready_chunk_id,
        pending_version_id=pending_version_id,
        secret_document_id=secret_document_id,
        ineligible_version_id=ineligible_version_id,
        entity_alpha=entity_alpha,
        entity_beta=entity_beta,
        statement_id=statement_id,
        vendor_chunk_id=vendor_chunk_id,
    )
    return seed, original_workspace, original_generation


def _cleanup(
    connection: psycopg.Connection,
    seed: _GraphQuerySeed,
    original_workspace: object,
    original_generation: object,
) -> None:
    """Restore the pointer and delete committed fixtures.

    Args:
        connection: Superuser connection.
        seed: Fixture identifiers.
        original_workspace: Pointer workspace id before the test.
        original_generation: Pointer generation before the test.
    """

    connection.rollback()
    connection.execute("SET ROLE postgres")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE app.graph_active_workspace_pointer
            SET workspace_id = %s, generation = %s
            WHERE id = %s::uuid
            """,
            (original_workspace, original_generation, GRAPH_POINTER_ID),
        )
        cursor.execute(
            """
            DELETE FROM app.documents
            WHERE id IN (
              SELECT document_id FROM app.document_versions
              WHERE id IN (%s, %s, %s)
            )
            """,
            (
                seed.ready_version_id,
                seed.pending_version_id,
                seed.ineligible_version_id,
            ),
        )
        cursor.execute(
            "DELETE FROM app.documents WHERE id = %s",
            (seed.secret_document_id,),
        )
        cursor.execute(
            """
            DELETE FROM app.graph_workspaces WHERE workspace_key = %s
            """,
            (seed.workspace_key,),
        )
        cursor.execute(
            """
            DELETE FROM app.graph_map_repair_jobs
            WHERE workspace_key = %s
            """,
            (seed.workspace_key,),
        )
    connection.commit()


def test_resolver_maps_inspection_acl_and_repair(
    db_connection: psycopg.Connection,
) -> None:
    """Authorized current maps survive; restricted stays invisible; repair queues."""

    db_connection.execute("SET ROLE postgres")
    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM pg_proc
            WHERE proname = 'inspect_graph_neighborhood'
            """
        )
        if cursor.fetchone() is None:
            pytest.skip("Packet 5 resolver migration is not applied")
        cursor.execute(
            """
            SELECT pg_get_functiondef(oid)
            FROM pg_proc
            WHERE proname = 'inspect_graph_neighborhood'
            """
        )
        inspect_row = cursor.fetchone()
        assert inspect_row is not None
        inspect_definition: object = inspect_row[0]
        inspect_sql = str(inspect_definition)
    assert "statement_timeout" in inspect_sql
    assert "'3s'" in inspect_sql
    assert "200" in inspect_sql

    seed, original_workspace, original_generation = _seed(db_connection)
    try:
        snapshot = load_query_workspace(db_connection)
        assert snapshot.state == "active"
        assert snapshot.pointer_attached is True
        assert snapshot.workspace_key == seed.workspace_key
        assert snapshot.config_generation == seed.config_generation

        leads = GraphLeadSet(
            mode="hybrid",
            entities=(
                GraphLeadEntity(
                    entity_name="Alpha", source_ids=(seed.vendor_chunk_id,)
                ),
                GraphLeadEntity(entity_name="Beta", source_ids=(seed.vendor_chunk_id,)),
            ),
            relations=(
                GraphLeadRelation(
                    src_id="Alpha",
                    tgt_id="Beta",
                    source_ids=(seed.vendor_chunk_id,),
                ),
                GraphLeadRelation(
                    src_id="Missing",
                    tgt_id="Ghost",
                    source_ids=("unmapped-chunk",),
                ),
            ),
        )
        outcome = resolve_graph_leads(
            db_connection,
            caller=seed.member,
            leads=leads,
            snapshot=snapshot,
        )
        assert outcome.returned_candidates == 2
        assert outcome.supported_candidates == 1
        assert outcome.candidates[0].object_id == seed.statement_id
        assert seed.ready_chunk_id in outcome.candidates[0].canonical_chunk_ids
        assert "candidate_dropped" in outcome.diagnostics
        enqueue_query_repairs(db_connection, snapshot=snapshot, dropped=outcome.dropped)
        db_connection.commit()
        db_connection.execute("SET ROLE postgres")
        with db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT map_kind, reason
                FROM app.graph_map_repair_jobs
                WHERE workspace_key = %s
                """,
                (seed.workspace_key,),
            )
            repair = cursor.fetchone()
        db_connection.commit()
        assert repair is not None
        assert repair[0] == GRAPH_QUERY_REPAIR_MAP_KIND
        assert repair[1] == "candidate_dropped"

        member_counts = visibility_counts(
            db_connection,
            caller=seed.member,
            relevant_version_ids=(
                seed.pending_version_id,
                seed.ineligible_version_id,
            ),
        )
        stranger_counts = visibility_counts(
            db_connection,
            caller=seed.stranger,
            relevant_version_ids=(
                seed.pending_version_id,
                seed.ineligible_version_id,
            ),
        )
        assert member_counts.partial_readiness_count >= 1
        assert member_counts.acl_blindness_count >= 1
        assert stranger_counts.partial_readiness_count >= 1
        assert stranger_counts.acl_blindness_count == 0

        member_inspect = inspect_graph(
            db_connection,
            caller=seed.member,
            snapshot=snapshot,
            entity_keys=(seed.entity_alpha,),
            depth=3,
        )
        assert member_inspect.row_count >= 1
        assert member_inspect.depth == 3
        assert all(node.hop <= 3 for node in member_inspect.nodes)
        types = {node.object_type for node in member_inspect.nodes}
        assert "entity" in types
        dumped = member_inspect.model_dump_json()
        assert "description" not in dumped
        assert "SecretOrg" not in dumped

        secret_member = inspect_graph(
            db_connection,
            caller=seed.member,
            snapshot=snapshot,
            document_id=seed.secret_document_id,
            depth=3,
        )
        secret_stranger = inspect_graph(
            db_connection,
            caller=seed.stranger,
            snapshot=snapshot,
            document_id=seed.secret_document_id,
            depth=3,
        )
        assert secret_member.row_count == 0
        assert secret_stranger.row_count == 0
        dumped_secret = secret_member.model_dump_json()
        assert "Secret Graph Doc" not in dumped_secret
        assert "Ineligible Restricted" not in dumped_secret
    finally:
        _cleanup(db_connection, seed, original_workspace, original_generation)
