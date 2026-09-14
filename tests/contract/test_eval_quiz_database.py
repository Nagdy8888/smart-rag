"""Hosted quiz-case schema, privilege, and RPC contract tests (P06-28)."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from tests.contract.integration_support import require_supabase_db_url, try_connect
from tests.contract.test_rls_matrix import rls_auth_version, rls_insert_profile

_CREATE_SQL = """
SELECT case_id, row_version, replayed
FROM app.create_eval_quiz_case(
  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""


def _payload_hash(seed: str) -> str:
    """Return a 64-character hex digest for idempotency payloads.

    Args:
        seed: Stable test-only payload identity. Never a question.

    Returns:
        SHA-256 hex digest.
    """

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield a rollback Postgres connection or skip when the fixture is down."""

    url = require_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip("Local destructive Supabase fixture unreachable")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def _seed_corpus(cursor: psycopg.Cursor) -> dict[str, Any]:
    """Insert owner/member users, one document version, chunks, and a run.

    Args:
        cursor: Open postgres-role cursor.

    Returns:
        Fixture identifiers. Question text is a short dummy, never logged.
    """

    owner_id = uuid4()
    member_id = uuid4()
    viewer_id = uuid4()
    disabled_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    other_document_id = uuid4()
    other_version_id = uuid4()
    chunk_a = uuid4()
    chunk_b = uuid4()
    chunk_c = uuid4()
    chunk_d = uuid4()
    other_chunk = uuid4()
    conversation_id = uuid4()
    run_id = uuid4()
    foreign_run_id = uuid4()

    rls_insert_profile(cursor, user_id=owner_id, role="owner")
    rls_insert_profile(cursor, user_id=member_id, role="member")
    rls_insert_profile(cursor, user_id=viewer_id, role="viewer")
    rls_insert_profile(cursor, user_id=disabled_id, role="owner", disabled=True)
    cursor.execute(
        """
        INSERT INTO app.documents (id, title, visibility, created_by)
        VALUES
          (%s, 'Quiz fixture', 'company_visible', %s),
          (%s, 'Other doc', 'company_visible', %s)
        """,
        (document_id, owner_id, other_document_id, owner_id),
    )
    cursor.execute(
        """
        INSERT INTO app.document_versions (
          id, document_id, version_number, status, retrieval_eligible,
          storage_bucket, storage_path
        )
        VALUES
          (%s, %s, 1, 'hybrid_ready', true, 'documents', 'quiz/a.bin'),
          (%s, %s, 1, 'hybrid_ready', true, 'documents', 'quiz/b.bin')
        """,
        (version_id, document_id, other_version_id, other_document_id),
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
        SET current_version_id = %s
        WHERE id = %s
        """,
        (other_version_id, other_document_id),
    )
    cursor.execute(
        """
        INSERT INTO app.document_chunks (
          id, document_id, version_id, chunk_index, raw_text, page_number,
          section_path, provenance
        )
        VALUES
          (%s, %s, %s, 0, 'alpha', 2, ARRAY['Intro'],
           '{"locators":[{"page_label":"ii"}]}'::jsonb),
          (%s, %s, %s, 1, 'beta', 3, ARRAY['Intro'],
           '{"locators":[{"page_label":"iii"}]}'::jsonb),
          (%s, %s, %s, 2, 'gamma', 4, ARRAY['Body'],
           '{"locators":[{"page_label":"4"}]}'::jsonb),
          (%s, %s, %s, 3, 'delta', 5, ARRAY['Body'],
           '{"locators":[{"page_label":"5"}]}'::jsonb),
          (%s, %s, %s, 0, 'other', 1, ARRAY['Other'],
           '{"locators":[{"page_label":"1"}]}'::jsonb)
        """,
        (
            chunk_a,
            document_id,
            version_id,
            chunk_b,
            document_id,
            version_id,
            chunk_c,
            document_id,
            version_id,
            chunk_d,
            document_id,
            version_id,
            other_chunk,
            other_document_id,
            other_version_id,
        ),
    )
    cursor.execute(
        """
        INSERT INTO app.conversations (id, creator_user_id, title)
        VALUES (%s, %s, 'quiz-run'), (%s, %s, 'foreign-run')
        """,
        (conversation_id, owner_id, uuid4(), member_id),
    )
    member_conversation = uuid4()
    cursor.execute(
        """
        INSERT INTO app.conversations (id, creator_user_id, title)
        VALUES (%s, %s, 'member-run')
        """,
        (member_conversation, member_id),
    )
    cursor.execute(
        """
        INSERT INTO app.runs (id, conversation_id, creator_user_id, status)
        VALUES
          (%s, %s, %s, 'completed'),
          (%s, %s, %s, 'completed')
        """,
        (run_id, conversation_id, owner_id, foreign_run_id, member_conversation, member_id),
    )
    cursor.execute(
        """
        INSERT INTO app.messages (conversation_id, role, content, run_id)
        VALUES (%s, 'user', 'What is alpha?', %s),
               (%s, 'user', 'Member question', %s)
        """,
        (conversation_id, run_id, member_conversation, foreign_run_id),
    )
    authz = rls_auth_version(cursor)
    return {
        "owner_id": owner_id,
        "member_id": member_id,
        "viewer_id": viewer_id,
        "disabled_id": disabled_id,
        "document_id": document_id,
        "version_id": version_id,
        "chunk_a": chunk_a,
        "chunk_b": chunk_b,
        "chunk_c": chunk_c,
        "chunk_d": chunk_d,
        "other_chunk": other_chunk,
        "run_id": run_id,
        "foreign_run_id": foreign_run_id,
        "authz": authz,
    }


def _create(
    cursor: psycopg.Cursor,
    seed: dict[str, Any],
    *,
    key: str,
    payload: str,
    split: str = "development",
    family: str | None = "family-01",
    chunks: list[UUID] | None = None,
    expected_answer: str = "alpha is a term",
    query_class: str = "factual_definition",
    source_run_id: UUID | None = None,
    question: str | None = None,
    generated_only: bool = True,
    user_id: UUID | None = None,
    role: str = "owner",
    authz: int | None = None,
) -> tuple[UUID, int, bool]:
    """Call create_eval_quiz_case as app_api.

    Args:
        cursor: Open cursor.
        seed: Fixture identifiers.
        key: Idempotency key.
        payload: Hash seed.
        split: Case split.
        family: Source family.
        chunks: Optional gold chunk IDs.
        expected_answer: Draft answer.
        query_class: Allowed positive class.
        source_run_id: Optional completed run.
        question: Used only when no run is supplied.
        generated_only: Draft flag.
        user_id: Caller. Defaults to owner.
        role: Caller role label.
        authz: Authorization version override.

    Returns:
        case_id, row_version, replayed.
    """

    cursor.execute("SET ROLE app_api")
    try:
        cursor.execute(
            _CREATE_SQL,
            (
                user_id or seed["owner_id"],
                role,
                authz if authz is not None else seed["authz"],
                source_run_id,
                question,
                expected_answer,
                [],
                query_class,
                [],
                split,
                family,
                generated_only,
                chunks or [],
                key,
                _payload_hash(payload),
            ),
        )
        row = cursor.fetchone()
    finally:
        cursor.execute("RESET ROLE")
    assert row is not None
    return UUID(str(row[0])), int(row[1]), bool(row[2])


def test_app_api_cannot_dml_eval_quiz_tables(
    db_connection: psycopg.Connection,
) -> None:
    """app_api has no direct INSERT/UPDATE/DELETE on quiz tables."""

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              has_table_privilege('app_api', 'app.eval_quiz_cases', 'INSERT'),
              has_table_privilege('app_api', 'app.eval_quiz_cases', 'UPDATE'),
              has_table_privilege('app_api', 'app.eval_quiz_cases', 'DELETE'),
              has_table_privilege('app_api', 'app.eval_quiz_gold_chunks', 'INSERT')
            """
        )
        row = cursor.fetchone()
    assert row == (False, False, False, False)


def test_browser_roles_cannot_execute_quiz_rpcs(
    db_connection: psycopg.Connection,
) -> None:
    """PUBLIC/anon/authenticated cannot execute quiz RPCs."""

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pg_get_function_identity_arguments(p.oid)
            FROM pg_proc AS p
            INNER JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'app' AND p.proname = 'create_eval_quiz_case'
            """
        )
        identity = cursor.fetchone()
        assert identity is not None
        signature = f"app.create_eval_quiz_case({identity[0]})"
        cursor.execute(
            """
            SELECT
              has_function_privilege('anon', %s, 'execute'),
              has_function_privilege('authenticated', %s, 'execute'),
              has_function_privilege('app_api', %s, 'execute')
            """,
            (signature, signature, signature),
        )
        row = cursor.fetchone()
    assert row == (False, False, True)


def test_owner_create_from_run_and_member_denied(
    db_connection: psycopg.Connection,
) -> None:
    """Owner create loads the run question; members are forbidden."""

    with db_connection.cursor() as cursor:
        seed = _seed_corpus(cursor)
        case_id, version, replayed = _create(
            cursor,
            seed,
            key="create-run-01",
            payload="create-run-01",
            source_run_id=seed["run_id"],
            chunks=[seed["chunk_a"]],
        )
        assert replayed is False
        assert version == 1
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT question, jsonb_array_length(gold), review_status
            FROM app.get_eval_quiz_case(%s, 'owner', %s, %s)
            """,
            (seed["owner_id"], seed["authz"], case_id),
        )
        got = cursor.fetchone()
        assert got is not None
        assert got[0] == "What is alpha?"
        assert got[1] == 1
        assert got[2] == "draft"
        cursor.execute(
            """
            SELECT case_id, split, query_class
            FROM app.list_eval_quiz_case_summaries(
              %s, 'owner', %s, 'development', NULL, 20, NULL
            )
            """,
            (seed["owner_id"], seed["authz"]),
        )
        listed = cursor.fetchall()
        assert any(row[0] == case_id for row in listed)
        cursor.execute("SAVEPOINT member_create")
        with pytest.raises(psycopg.errors.RaiseException, match="eval_quiz:forbidden"):
            cursor.execute(
                _CREATE_SQL,
                (
                    seed["member_id"],
                    "member",
                    seed["authz"],
                    seed["run_id"],
                    None,
                    "x",
                    [],
                    "factual_definition",
                    [],
                    "development",
                    "family-01",
                    True,
                    [],
                    "member-key-01",
                    _payload_hash("member"),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT member_create")
        cursor.execute("RESET ROLE")


def test_foreign_run_and_inaccessible_chunk_are_not_found(
    db_connection: psycopg.Connection,
) -> None:
    """Foreign runs and unauthorized gold are indistinguishable 404s."""

    with db_connection.cursor() as cursor:
        seed = _seed_corpus(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT foreign_run")
        with pytest.raises(psycopg.errors.RaiseException, match="eval_quiz:not_found"):
            cursor.execute(
                _CREATE_SQL,
                (
                    seed["owner_id"],
                    "owner",
                    seed["authz"],
                    seed["foreign_run_id"],
                    None,
                    "x",
                    [],
                    "factual_definition",
                    [],
                    "development",
                    "family-01",
                    True,
                    [],
                    "foreign-run-01",
                    _payload_hash("foreign"),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT foreign_run")
        cursor.execute("SAVEPOINT missing_chunk")
        with pytest.raises(psycopg.errors.RaiseException, match="eval_quiz:not_found"):
            cursor.execute(
                _CREATE_SQL,
                (
                    seed["owner_id"],
                    "owner",
                    seed["authz"],
                    seed["run_id"],
                    None,
                    "x",
                    [],
                    "factual_definition",
                    [],
                    "development",
                    "family-01",
                    True,
                    [uuid4()],
                    "missing-chunk-01",
                    _payload_hash("missing-chunk"),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT missing_chunk")
        cursor.execute("RESET ROLE")


def test_holdout_stale_auth_and_disabled_denied(
    db_connection: psycopg.Connection,
) -> None:
    """Holdout tokens, stale auth, forged role, and disabled users fail closed."""

    with db_connection.cursor() as cursor:
        seed = _seed_corpus(cursor)
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT holdout")
        with pytest.raises(psycopg.errors.RaiseException, match="eval_quiz:holdout_rejected"):
            cursor.execute(
                _CREATE_SQL,
                (
                    seed["owner_id"],
                    "owner",
                    seed["authz"],
                    seed["run_id"],
                    None,
                    "x",
                    [],
                    "factual_definition",
                    [],
                    "holdout",
                    "family-01",
                    True,
                    [],
                    "holdout-key-01",
                    _payload_hash("holdout"),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT holdout")
        cursor.execute("SAVEPOINT stale")
        with pytest.raises(
            psycopg.errors.RaiseException, match="eval_quiz:authorization_rejected"
        ):
            cursor.execute(
                _CREATE_SQL,
                (
                    seed["owner_id"],
                    "owner",
                    seed["authz"] + 1,
                    seed["run_id"],
                    None,
                    "x",
                    [],
                    "factual_definition",
                    [],
                    "development",
                    "family-01",
                    True,
                    [],
                    "stale-key-01",
                    _payload_hash("stale"),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT stale")
        cursor.execute("SAVEPOINT forged")
        with pytest.raises(
            psycopg.errors.RaiseException, match="eval_quiz:authorization_rejected"
        ):
            cursor.execute(
                _CREATE_SQL,
                (
                    seed["owner_id"],
                    "member",
                    seed["authz"],
                    seed["run_id"],
                    None,
                    "x",
                    [],
                    "factual_definition",
                    [],
                    "development",
                    "family-01",
                    True,
                    [],
                    "forged-key-01",
                    _payload_hash("forged"),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT forged")
        cursor.execute("SAVEPOINT disabled")
        with pytest.raises(
            psycopg.errors.RaiseException, match="eval_quiz:authorization_rejected"
        ):
            cursor.execute(
                _CREATE_SQL,
                (
                    seed["disabled_id"],
                    "owner",
                    seed["authz"],
                    None,
                    "Disabled question",
                    "x",
                    [],
                    "factual_definition",
                    [],
                    "development",
                    "family-01",
                    True,
                    [],
                    "disabled-key-01",
                    _payload_hash("disabled"),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT disabled")
        cursor.execute("RESET ROLE")


def test_gold_bounds_family_isolation_and_approval_reset(
    db_connection: psycopg.Connection,
) -> None:
    """Fourth/duplicate/cross-doc gold, family split, CAS, and approval reset."""

    with db_connection.cursor() as cursor:
        seed = _seed_corpus(cursor)
        case_id, version, _ = _create(
            cursor,
            seed,
            key="gold-case-01",
            payload="gold-case-01",
            source_run_id=seed["run_id"],
            chunks=[seed["chunk_a"]],
            family="family-aa",
        )
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT fourth")
        with pytest.raises(psycopg.errors.RaiseException, match="eval_quiz:gold_limit"):
            cursor.execute(
                """
                SELECT * FROM app.replace_eval_quiz_gold(
                  %s, 'owner', %s, %s, %s, %s
                )
                """,
                (
                    seed["owner_id"],
                    seed["authz"],
                    case_id,
                    version,
                    [seed["chunk_a"], seed["chunk_b"], seed["chunk_c"], seed["chunk_d"]],
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT fourth")
        cursor.execute("SAVEPOINT duplicate")
        with pytest.raises(psycopg.errors.RaiseException, match="eval_quiz:gold_duplicate"):
            cursor.execute(
                """
                SELECT * FROM app.replace_eval_quiz_gold(
                  %s, 'owner', %s, %s, %s, %s
                )
                """,
                (
                    seed["owner_id"],
                    seed["authz"],
                    case_id,
                    version,
                    [seed["chunk_a"], seed["chunk_a"]],
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT duplicate")
        cursor.execute("SAVEPOINT cross_doc")
        with pytest.raises(
            psycopg.errors.RaiseException, match="eval_quiz:gold_version_mismatch"
        ):
            cursor.execute(
                """
                SELECT * FROM app.replace_eval_quiz_gold(
                  %s, 'owner', %s, %s, %s, %s
                )
                """,
                (
                    seed["owner_id"],
                    seed["authz"],
                    case_id,
                    version,
                    [seed["chunk_a"], seed["other_chunk"]],
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT cross_doc")
        cursor.execute(
            """
            SELECT case_id, row_version, gold_chunk_count
            FROM app.replace_eval_quiz_gold(
              %s, 'owner', %s, %s, %s, %s
            )
            """,
            (
                seed["owner_id"],
                seed["authz"],
                case_id,
                version,
                [seed["chunk_a"], seed["chunk_b"]],
            ),
        )
        replaced = cursor.fetchone()
        assert replaced is not None
        assert int(replaced[2]) == 2
        new_version = int(replaced[1])
        cursor.execute(
            """
            SELECT case_id, row_version
            FROM app.approve_eval_quiz_case(%s, 'owner', %s, %s, %s)
            """,
            (seed["owner_id"], seed["authz"], case_id, new_version),
        )
        approved = cursor.fetchone()
        assert approved is not None
        cursor.execute("SAVEPOINT stale_cas")
        with pytest.raises(
            psycopg.errors.RaiseException, match="eval_quiz:stale_row_version"
        ):
            cursor.execute(
                """
                SELECT * FROM app.patch_eval_quiz_case(
                  %s, 'owner', %s, %s, %s, NULL, 'changed', NULL, NULL, NULL, NULL, NULL
                )
                """,
                (seed["owner_id"], seed["authz"], case_id, version),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT stale_cas")
        cursor.execute(
            """
            SELECT case_id, row_version
            FROM app.patch_eval_quiz_case(
              %s, 'owner', %s, %s, %s, NULL, 'changed answer', NULL, NULL, NULL, NULL, NULL
            )
            """,
            (seed["owner_id"], seed["authz"], case_id, int(approved[1])),
        )
        patched = cursor.fetchone()
        assert patched is not None
        cursor.execute(
            """
            SELECT review_status, reviewer_user_id, reviewed_at, generated_only
            FROM app.get_eval_quiz_case(%s, 'owner', %s, %s)
            """,
            (seed["owner_id"], seed["authz"], case_id),
        )
        after_patch = cursor.fetchone()
        assert after_patch is not None
        assert after_patch[0] == "draft"
        assert after_patch[1] is None
        assert after_patch[2] is None
        cursor.execute("RESET ROLE")
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT family")
        with pytest.raises(
            psycopg.errors.RaiseException, match="eval_quiz:family_split_conflict"
        ):
            cursor.execute(
                _CREATE_SQL,
                (
                    seed["owner_id"],
                    "owner",
                    seed["authz"],
                    seed["run_id"],
                    None,
                    "x",
                    [],
                    "factual_definition",
                    [],
                    "qualification",
                    "family-aa",
                    True,
                    [],
                    "family-cross-01",
                    _payload_hash("family-cross"),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT family")
        cursor.execute("RESET ROLE")


def test_idempotency_replay_and_collision(
    db_connection: psycopg.Connection,
) -> None:
    """Same key+hash replays; a different payload is rejected."""

    with db_connection.cursor() as cursor:
        seed = _seed_corpus(cursor)
        first, version, replayed = _create(
            cursor,
            seed,
            key="idem-key-01",
            payload="same-payload",
            source_run_id=seed["run_id"],
        )
        assert replayed is False
        second, replay_version, replayed_again = _create(
            cursor,
            seed,
            key="idem-key-01",
            payload="same-payload",
            source_run_id=seed["run_id"],
        )
        assert replayed_again is True
        assert second == first
        assert replay_version == version
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT collision")
        with pytest.raises(
            psycopg.errors.RaiseException, match="eval_quiz:idempotency_collision"
        ):
            cursor.execute(
                _CREATE_SQL,
                (
                    seed["owner_id"],
                    "owner",
                    seed["authz"],
                    seed["run_id"],
                    None,
                    "changed",
                    [],
                    "factual_definition",
                    [],
                    "development",
                    "family-01",
                    True,
                    [],
                    "idem-key-01",
                    _payload_hash("other-payload"),
                ),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT collision")
        cursor.execute("RESET ROLE")


def test_expired_purge_is_bounded_and_content_free(
    db_connection: psycopg.Connection,
) -> None:
    """Expired purge deletes at most 60 rows and audits a count only."""

    with db_connection.cursor() as cursor:
        seed = _seed_corpus(cursor)
        case_id, _version, _ = _create(
            cursor,
            seed,
            key="purge-key-01",
            payload="purge-key-01",
            source_run_id=seed["run_id"],
        )
        cursor.execute(
            """
            UPDATE app.eval_quiz_cases
            SET expires_at = timezone('utc', now()) - interval '1 day'
            WHERE id = %s
            """,
            (case_id,),
        )
        cursor.execute("SET ROLE app_api")
        cursor.execute(
            """
            SELECT purged_count
            FROM app.purge_expired_eval_quiz_cases(%s, 'owner', %s)
            """,
            (seed["owner_id"], seed["authz"]),
        )
        purged = cursor.fetchone()
        assert purged is not None
        assert int(purged[0]) >= 1
        cursor.execute("SAVEPOINT purged_get")
        with pytest.raises(psycopg.errors.RaiseException, match="eval_quiz:not_found"):
            cursor.execute(
                """
                SELECT case_id FROM app.get_eval_quiz_case(%s, 'owner', %s, %s)
                """,
                (seed["owner_id"], seed["authz"], case_id),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT purged_get")
        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT payload
            FROM app.audit_events
            WHERE event_type = 'eval_quiz_case_purge'
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        audit = cursor.fetchone()
        assert audit is not None
        payload = audit[0]
        assert "purged_count" in payload
        assert "question" not in payload
        assert "expected_answer" not in payload


def test_zero_gold_draft_cannot_approve(
    db_connection: psycopg.Connection,
) -> None:
    """Zero gold is allowed for drafts and blocked at approval."""

    with db_connection.cursor() as cursor:
        seed = _seed_corpus(cursor)
        case_id, version, _ = _create(
            cursor,
            seed,
            key="zero-gold-01",
            payload="zero-gold-01",
            source_run_id=seed["run_id"],
            chunks=[],
        )
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT approve_zero")
        with pytest.raises(psycopg.errors.RaiseException, match="eval_quiz:gold_required"):
            cursor.execute(
                """
                SELECT * FROM app.approve_eval_quiz_case(%s, 'owner', %s, %s, %s)
                """,
                (seed["owner_id"], seed["authz"], case_id, version),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT approve_zero")
        cursor.execute("RESET ROLE")


def test_concurrent_create_cannot_exceed_sixty(db_url: str) -> None:
    """Workspace lock prevents a 61st live case under concurrent creates."""

    setup = try_connect(db_url)
    if setup is None:
        pytest.skip("Local destructive Supabase fixture unreachable")
    owner_id = uuid4()
    try:
        setup.autocommit = False
        with setup.cursor() as cursor:
            rls_insert_profile(cursor, user_id=owner_id, role="owner")
            authz = rls_auth_version(cursor)
            cursor.execute(
                """
                INSERT INTO app.eval_quiz_cases (
                  creator_user_id, question, query_class, split, review_status,
                  generated_only, idempotency_key, request_payload_hash, expires_at
                )
                SELECT
                  %s,
                  'capacity filler',
                  'factual_definition',
                  'development',
                  'draft',
                  true,
                  'fill-key-' || lpad(gs::text, 4, '0'),
                  repeat('ab', 32),
                  timezone('utc', now()) + interval '365 days'
                FROM generate_series(1, 59) AS gs
                """,
                (owner_id,),
            )
        setup.commit()
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            """Create one additional live case after the barrier."""

            connection = psycopg.connect(db_url)
            connection.autocommit = False
            try:
                connection.execute("SET ROLE app_api")
                barrier.wait(timeout=15)
                try:
                    connection.execute(
                        _CREATE_SQL,
                        (
                            owner_id,
                            "owner",
                            authz,
                            None,
                            f"capacity question {index}",
                            "answer",
                            [],
                            "factual_definition",
                            [],
                            "development",
                            f"family-c{index}",
                            True,
                            [],
                            f"cap-live-{index:02d}",
                            _payload_hash(f"cap-live-{index}"),
                        ),
                    )
                    connection.commit()
                    with lock:
                        outcomes.append("ok")
                except Exception as exc:
                    connection.rollback()
                    with lock:
                        outcomes.append(str(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(index,)) for index in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert outcomes.count("ok") == 1
        assert any("eval_quiz:capacity_exceeded" in item for item in outcomes)
        with setup.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)::integer
                FROM app.eval_quiz_cases
                WHERE expires_at > timezone('utc', now())
                  AND creator_user_id = %s
                """,
                (owner_id,),
            )
            live = cursor.fetchone()
            assert live is not None
            assert int(live[0]) == 60
    finally:
        with setup.cursor() as cursor:
            cursor.execute(
                "DELETE FROM app.eval_quiz_cases WHERE creator_user_id = %s",
                (owner_id,),
            )
            cursor.execute("DELETE FROM app.profiles WHERE user_id = %s", (owner_id,))
        setup.commit()
        setup.close()
