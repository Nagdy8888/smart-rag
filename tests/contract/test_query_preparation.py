"""Contract tests for query memory load, counted prep, and branch inheritance."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_admission.service import admit_query_run
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.branches import execute_branches
from smart_rag_core.query_routing.exceptions import QueryRoutingError
from smart_rag_core.query_routing.matrix import compile_retrieval_plan
from smart_rag_core.query_routing.memory import load_authorized_memory
from smart_rag_core.query_routing.models import PreparationModelPayload
from smart_rag_core.query_routing.preparation import prepare_query
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.contract.integration_support import (
    REPO_ROOT,
    resolve_supabase_db_url,
    try_connect,
)


def _ensure_local_postgres() -> str:
    """Return a reachable local Supabase URL, starting the CLI stack if needed.

    Returns:
        Postgres URL on port 54322 when reachable.

    Raises:
        pytest.skip: When the stack cannot be started in this environment.
    """

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is not None:
        connection.close()
        return url

    import shutil
    import subprocess

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        pytest.skip("pnpm is unavailable; local Supabase contract not run")
    started = subprocess.run(  # noqa: S603 - pinned pnpm starts local CLI stack
        [pnpm, "exec", "supabase", "start"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    if started.returncode != 0:
        pytest.skip(
            "local Supabase start failed: " + (started.stderr or started.stdout)[-500:]
        )
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.close()
    return url


@pytest.fixture
def db_url() -> str:
    """Yield the local Supabase URL or skip."""

    return _ensure_local_postgres()


@pytest.fixture
def db_connection(db_url: str) -> Iterator[psycopg.Connection]:
    """Yield one postgres-role connection with rollback on exit."""

    connection = psycopg.connect(db_url)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def _insert_user_profile(
    cursor: psycopg.Cursor,
    *,
    user_id: UUID,
    role: str,
) -> None:
    """Insert one Auth user and application profile."""

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
        """,
        (user_id, f"{user_id}@example.com"),
    )
    cursor.execute(
        """
        INSERT INTO app.profiles (user_id, role, monthly_llm_budget_usd)
        VALUES (%s, %s::app.user_role, %s)
        """,
        (user_id, role, Decimal("200.00")),
    )


def _insert_conversation(
    cursor: psycopg.Cursor,
    *,
    user_id: UUID,
    conversation_id: UUID | None = None,
) -> UUID:
    """Insert one undeleted conversation owned by ``user_id``."""

    conv_id = conversation_id or uuid4()
    cursor.execute(
        """
        INSERT INTO app.conversations (id, creator_user_id, title)
        VALUES (%s, %s, 'query memory fixture')
        """,
        (conv_id, user_id),
    )
    return conv_id


def _authorization_version(cursor: psycopg.Cursor) -> int:
    """Return the live company authorization version."""

    row = cursor.execute("SELECT app.current_authorization_version()").fetchone()
    assert row is not None
    return int(row[0])


def _expect_memory_error(
    connection: psycopg.Connection,
    *,
    match: str,
    caller: CallerContext,
    conversation_id: UUID,
) -> None:
    """Expect a memory-load failure and roll back the aborted RPC.

    Args:
        connection: Open test connection, typically ``SET ROLE app_api``.
        match: Reason substring.
        caller: Caller under test.
        conversation_id: Conversation id passed to the RPC.
    """

    connection.execute("SAVEPOINT memory_error")
    try:
        with pytest.raises(QueryRoutingError, match=match):
            load_authorized_memory(
                connection,
                caller=caller,
                conversation_id=conversation_id,
            )
    finally:
        connection.execute("ROLLBACK TO SAVEPOINT memory_error")
        connection.execute("RELEASE SAVEPOINT memory_error")


def _caller(user_id: UUID, role: str, authorization_version: int) -> CallerContext:
    """Build a server-shaped caller context.

    Args:
        user_id: Profile user id.
        role: Live profile role.
        authorization_version: Company authorization version.

    Returns:
        Server-derived caller context.
    """

    return CallerContext(
        user_id=str(user_id),
        role=UserRole(role),
        authorization_version=authorization_version,
    )


def test_memory_load_creator_only_and_deleted_fails(
    db_connection: psycopg.Connection,
) -> None:
    """Creator-only memory load succeeds; foreign and deleted conversations fail."""

    creator_id = uuid4()
    stranger_id = uuid4()
    conversation_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=creator_id, role="member")
        _insert_user_profile(cursor, user_id=stranger_id, role="owner")
        _insert_conversation(
            cursor, user_id=creator_id, conversation_id=conversation_id
        )
        cursor.execute(
            """
            INSERT INTO app.messages (conversation_id, role, content)
            VALUES (%s, 'user', 'first'), (%s, 'assistant', 'second')
            """,
            (conversation_id, conversation_id),
        )
        version = _authorization_version(cursor)
    db_connection.commit()
    db_connection.execute("SET ROLE app_api")
    creator = _caller(creator_id, "member", version)
    records = load_authorized_memory(
        db_connection,
        caller=creator,
        conversation_id=conversation_id,
    )
    assert len(records) == 2
    assert all("<<untrusted-memory" in item.delimited for item in records)
    assert all("source document" not in item.content.lower() for item in records)

    stranger = _caller(stranger_id, "owner", version)
    _expect_memory_error(
        db_connection,
        match="conversation_forbidden",
        caller=stranger,
        conversation_id=conversation_id,
    )

    db_connection.execute("RESET ROLE")
    db_connection.execute(
        "UPDATE app.conversations SET deleted_at = timezone('utc', now()) WHERE id = %s",
        (conversation_id,),
    )
    db_connection.commit()
    db_connection.execute("SET ROLE app_api")
    _expect_memory_error(
        db_connection,
        match="conversation_deleted",
        caller=creator,
        conversation_id=conversation_id,
    )


def test_counted_prep_consumes_profile_kind(
    db_connection: psycopg.Connection,
) -> None:
    """Model-assisted preparation consumes exactly one ``profile`` usage row."""

    user_id = uuid4()
    conversation_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        _insert_conversation(cursor, user_id=user_id, conversation_id=conversation_id)
        version = _authorization_version(cursor)
    db_connection.commit()
    caller = _caller(user_id, "member", version)
    payload_hash = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.COMPOSITE,
        message="What is the status of INV-SR-1001?",
    )
    db_connection.execute("SET ROLE app_api")
    admitted = admit_query_run(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        idempotency_key=uuid4(),
        payload_hash=payload_hash,
        route_family=Phase6RouteFamily.COMPOSITE,
        token_issued_at=datetime.now(),
    )
    db_connection.commit()

    def _caller_model(query: str, memory: object) -> PreparationModelPayload:
        """Return a fixed preparation payload.

        Args:
            query: User query text.
            memory: Unused memory snapshot.

        Returns:
            Deterministic preparation model payload.
        """

        del memory
        return PreparationModelPayload(
            rewrite=query,
            confidence=0.7,
            hl_keywords=("status",),
            ll_keywords=("INV-SR-1001",),
        )

    prep = prepare_query(
        "What is the status of INV-SR-1001?",
        runtime=admitted.context,
        model_caller=_caller_model,
        force_model=True,
        connection=db_connection,
        caller=caller,
    )
    db_connection.commit()
    assert prep.model_calls == 1
    db_connection.execute("RESET ROLE")
    with db_connection.cursor() as cursor:
        row = cursor.execute(
            """
            SELECT usage_kind, COUNT(*)
            FROM app.llm_usage
            WHERE run_id = %s
            GROUP BY usage_kind
            """,
            (admitted.context.run_id,),
        ).fetchall()
    kinds = {str(item[0]): int(item[1]) for item in row}
    assert kinds.get("profile") == 1
    assert "rewrite" not in kinds


def test_branch_results_inherit_run_and_reservation(
    db_connection: psycopg.Connection,
) -> None:
    """Every branch copies packet 1 run_id and reservation_id."""

    user_id = uuid4()
    conversation_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        _insert_conversation(cursor, user_id=user_id, conversation_id=conversation_id)
        version = _authorization_version(cursor)
    db_connection.commit()
    caller = _caller(user_id, "member", version)
    payload_hash = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.COMPOSITE,
        message="Hello",
    )
    db_connection.execute("SET ROLE app_api")
    admitted = admit_query_run(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        idempotency_key=uuid4(),
        payload_hash=payload_hash,
        route_family=Phase6RouteFamily.COMPOSITE,
        token_issued_at=datetime.now(),
    )
    db_connection.commit()
    prep = prepare_query("Hello", runtime=admitted.context)
    plan = compile_retrieval_plan(prep, admitted.context)
    results = execute_branches(plan, prep, admitted.context)
    assert results
    assert all(item.run_id == admitted.context.run_id for item in results)
    assert all(
        item.reservation_id == admitted.context.reservation_id for item in results
    )
    assert all(item.keyword_extract_count == 0 for item in results)
    assert all(item.catalog_llm_call_count == 0 for item in results)
    assert all(item.company_claim is False for item in results)
