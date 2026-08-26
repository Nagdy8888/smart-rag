"""Local Postgres bootstrap and admission-row helpers for query contracts."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_admission.service import QueryAdmissionResult, admit_query_run
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import CallerContext, UserRole

from tests.contract.integration_support import (
    REPO_ROOT,
    resolve_supabase_db_url,
    try_connect,
)


def ensure_local_postgres() -> str:
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


def insert_user_profile(
    cursor: psycopg.Cursor,
    *,
    user_id: UUID,
    role: str,
    monthly_llm_budget_usd: Decimal | None = None,
) -> None:
    """Insert one Auth user and application profile.

    Args:
        cursor: Open postgres-role cursor.
        user_id: Profile subject.
        role: Application role.
        monthly_llm_budget_usd: Optional monthly USD cap.
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
        """,
        (user_id, f"{user_id}@example.com"),
    )
    cursor.execute(
        """
        INSERT INTO app.profiles (user_id, role, monthly_llm_budget_usd)
        VALUES (%s, %s::app.user_role, %s)
        """,
        (user_id, role, monthly_llm_budget_usd),
    )


def insert_conversation(
    cursor: psycopg.Cursor,
    *,
    user_id: UUID,
    conversation_id: UUID | None = None,
) -> UUID:
    """Insert one undeleted conversation owned by ``user_id``.

    Args:
        cursor: Open postgres-role cursor.
        user_id: Conversation owner.
        conversation_id: Optional stable id.

    Returns:
        Conversation UUID.
    """

    conv_id = conversation_id or uuid4()
    cursor.execute(
        """
        INSERT INTO app.conversations (id, creator_user_id, title)
        VALUES (%s, %s, 'query admission fixture')
        """,
        (conv_id, user_id),
    )
    return conv_id


def authorization_version(cursor: psycopg.Cursor) -> int:
    """Return the live company authorization version.

    Args:
        cursor: Open cursor.

    Returns:
        Current authorization version.
    """

    row = cursor.execute("SELECT app.current_authorization_version()").fetchone()
    assert row is not None
    return int(row[0])


def caller_context(
    user_id: UUID,
    role: str,
    authorization_version: int,
    *,
    session_id: str | None = None,
    disabled: bool = False,
) -> CallerContext:
    """Build a server-shaped caller context for RPC tests.

    Args:
        user_id: Subject.
        role: Application role.
        authorization_version: Live version.
        session_id: Optional session.
        disabled: Disabled flag.

    Returns:
        Caller context.
    """

    return CallerContext(
        user_id=str(user_id),
        role=UserRole(role),
        authorization_version=authorization_version,
        session_id=session_id,
        disabled=disabled,
    )


def admit(
    connection: psycopg.Connection,
    *,
    caller: CallerContext,
    conversation_id: UUID,
    message: str = "what is the policy",
    route_family: Phase6RouteFamily = Phase6RouteFamily.HYBRID,
    idempotency_key: UUID | None = None,
    token_issued_at: datetime | None = None,
) -> tuple[QueryAdmissionResult, UUID]:
    """Admit one run as ``app_api`` and return the result plus key.

    Args:
        connection: Open test connection.
        caller: Server-derived caller.
        conversation_id: Conversation id.
        message: User text hashed into the payload.
        route_family: Reserved envelope.
        idempotency_key: Optional stable key.
        token_issued_at: Optional issued-at stamp.

    Returns:
        Admission result and idempotency key.
    """

    key = idempotency_key or uuid4()
    payload_hash = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=route_family,
        message=message,
    )
    connection.execute("SET ROLE app_api")
    result = admit_query_run(
        connection,
        caller=caller,
        conversation_id=conversation_id,
        idempotency_key=key,
        payload_hash=payload_hash,
        route_family=route_family,
        token_issued_at=token_issued_at,
    )
    connection.execute("RESET ROLE")
    return result, key


@pytest.fixture
def db_url() -> str:
    """Yield the local Supabase URL or skip."""

    return ensure_local_postgres()


@pytest.fixture
def db_connection(db_url: str) -> Iterator[psycopg.Connection]:
    """Yield one postgres-role connection with rollback on exit."""

    connection = psycopg.connect(db_url)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def admit_error(
    connection: psycopg.Connection,
    match: str,
    **kwargs: object,
) -> None:
    """Expect a typed admission failure and roll back to a savepoint.

    Args:
        connection: Open test connection.
        match: Reason substring.
        **kwargs: Forwarded to ``admit``.
    """

    connection.execute("SAVEPOINT admit_error")
    try:
        with pytest.raises(QueryAdmissionError, match=match):
            admit(connection, **kwargs)  # pyright: ignore[reportArgumentType]
    finally:
        connection.execute("ROLLBACK TO SAVEPOINT admit_error")
        connection.execute("RESET ROLE")
        connection.execute("RELEASE SAVEPOINT admit_error")


def retire_committed_query_run(
    db_url: str,
    *,
    run_id: UUID,
    reservation_id: UUID,
) -> None:
    """Close a committed fixture run so it cannot consume QT-CAP-004.

    Args:
        db_url: Local Postgres URL.
        run_id: Run inserted by a test that had to commit across connections.
        reservation_id: Matching ``query_run`` reservation.
    """

    with psycopg.connect(db_url) as connection:
        connection.execute(
            """
            UPDATE app.runs
            SET status = 'completed',
                completed_at = timezone('utc', now()),
                deadline_at = timezone('utc', now()) - interval '1 second'
            WHERE id = %s
            """,
            (run_id,),
        )
        connection.execute(
            """
            UPDATE app.budget_reservations
            SET status = 'released',
                committed_amount_usd = 0,
                remaining_usd = 0,
                released_at = timezone('utc', now())
            WHERE id = %s
            """,
            (reservation_id,),
        )
        connection.commit()
