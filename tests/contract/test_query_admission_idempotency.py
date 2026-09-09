"""Query-run admission reconnect and concurrent idempotency."""

from __future__ import annotations

import threading
from uuid import UUID, uuid4

import psycopg
import pytest
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.payload import hash_query_admission_payload
from smart_rag_core.query_admission.service import (
    admit_query_run,
    get_query_run,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.search_scope import RequestedSearchScope

from tests.support.query_postgres import (
    admit as _admit,
)
from tests.support.query_postgres import admit_error as _admit_error
from tests.support.query_postgres import (
    authorization_version as _authorization_version,
)
from tests.support.query_postgres import (
    caller_context as _caller,
)
from tests.support.query_postgres import (
    insert_conversation as _insert_conversation,
)
from tests.support.query_postgres import (
    insert_user_profile as _insert_user_profile,
)
from tests.support.query_postgres import (
    retire_committed_query_run as _retire_committed_query_run,
)


def test_admit_reconnects_same_key_and_rejects_payload_collision(
    db_connection: psycopg.Connection,
) -> None:
    """Same key+hash reconnects; same key+different hash fails closed."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    caller = _caller(user_id, "member", version)
    first, key = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="same",
    )
    second, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="same",
        idempotency_key=key,
    )
    assert first.reconnect is False
    assert second.reconnect is True
    assert second.context.run_id == first.context.run_id
    assert second.context.reservation_id == first.context.reservation_id

    _admit_error(
        db_connection,
        "key_collision",
        caller=caller,
        conversation_id=conversation_id,
        message="changed",
        idempotency_key=key,
    )

    with db_connection.cursor() as cursor:
        count = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.runs
            WHERE creator_user_id = %s AND conversation_id = %s
            """,
            (user_id, conversation_id),
        ).fetchone()
        reservations = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.budget_reservations
            WHERE user_id = %s AND reservation_kind = 'query_run'
            """,
            (user_id,),
        ).fetchone()
    assert count == (1,)
    assert reservations == (1,)


def test_concurrent_duplicate_admit_converges_on_one_run(
    db_url: str,
    db_connection: psycopg.Connection,
) -> None:
    """Two connections with the same key create one run and one reservation."""

    user_id = uuid4()
    key = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    db_connection.commit()
    caller = _caller(user_id, "member", version)
    payload_hash = hash_query_admission_payload(
        conversation_id=conversation_id,
        route_family=Phase6RouteFamily.HYBRID,
        message="concurrent",
        requested_search_scope=RequestedSearchScope.AUTO,
    )
    barrier = threading.Barrier(2)
    run_ids: list[UUID] = []
    reservation_ids: list[UUID] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        """Admit once from a dedicated connection after the barrier."""

        with psycopg.connect(db_url) as connection:
            connection.execute("SET ROLE app_api")
            barrier.wait(timeout=10)
            try:
                result = admit_query_run(
                    connection,
                    caller=caller,
                    conversation_id=conversation_id,
                    idempotency_key=key,
                    payload_hash=payload_hash,
                    route_family=Phase6RouteFamily.HYBRID,
                    requested_search_scope=RequestedSearchScope.AUTO,
                )
                connection.commit()
                with lock:
                    run_ids.append(result.context.run_id)
                    reservation_ids.append(result.context.reservation_id)
            except Exception as exc:
                connection.rollback()
                with lock:
                    errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert errors == []
    assert len(run_ids) == 2
    assert set(run_ids) == {run_ids[0]}
    assert set(reservation_ids) == {reservation_ids[0]}
    _retire_committed_query_run(
        db_url,
        run_id=run_ids[0],
        reservation_id=reservation_ids[0],
    )


def test_same_scope_reconnects_and_different_scope_collides(
    db_connection: psycopg.Connection,
) -> None:
    """Same key plus same scope reconnects; a different scope collides."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    caller = _caller(user_id, "member", version)
    first, key = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="Parallel Tool Execution",
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
    )
    second, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="Parallel Tool Execution",
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
        idempotency_key=key,
    )
    assert first.reconnect is False
    assert second.reconnect is True
    assert second.context.run_id == first.context.run_id
    assert (
        second.context.requested_search_scope is RequestedSearchScope.COMPANY_DOCUMENTS
    )
    _admit_error(
        db_connection,
        "key_collision",
        caller=caller,
        conversation_id=conversation_id,
        message="Parallel Tool Execution",
        requested_search_scope=RequestedSearchScope.GENERAL_KNOWLEDGE,
        idempotency_key=key,
    )


def test_invalid_search_scope_rejected_and_foreign_get_is_not_found(
    db_connection: psycopg.Connection,
) -> None:
    """Invalid SQL scope fails closed; foreign callers cannot read a run."""

    user_id = uuid4()
    stranger_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        _insert_user_profile(cursor, user_id=stranger_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    caller = _caller(user_id, "member", version)
    admitted, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
        message="Parallel Tool Execution",
        requested_search_scope=RequestedSearchScope.COMPANY_DOCUMENTS,
    )
    db_connection.execute("SET ROLE app_api")
    db_connection.execute("SAVEPOINT invalid_scope_update")
    try:
        with pytest.raises(psycopg.Error):
            db_connection.execute(
                """
                UPDATE app.runs
                SET requested_search_scope = 'world_knowledge'
                WHERE id = %s
                """,
                (admitted.context.run_id,),
            )
    finally:
        db_connection.execute("ROLLBACK TO SAVEPOINT invalid_scope_update")
        db_connection.execute("RELEASE SAVEPOINT invalid_scope_update")
    db_connection.execute("SAVEPOINT invalid_scope_rpc")
    try:
        with pytest.raises(psycopg.Error):
            db_connection.execute(
                """
                SELECT * FROM app.admit_query_run_v2(
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    caller.user_id,
                    caller.rpc_role(),
                    caller.rpc_authorization_version(),
                    conversation_id,
                    str(uuid4()),
                    "a" * 64,
                    Phase6RouteFamily.HYBRID.value,
                    "world_knowledge",
                    None,
                    None,
                ),
            )
    finally:
        db_connection.execute("ROLLBACK TO SAVEPOINT invalid_scope_rpc")
        db_connection.execute("RELEASE SAVEPOINT invalid_scope_rpc")
    owned = get_query_run(db_connection, caller=caller, run_id=admitted.context.run_id)
    assert owned.requested_search_scope is RequestedSearchScope.COMPANY_DOCUMENTS
    stranger = _caller(stranger_id, "member", version)
    with pytest.raises(QueryAdmissionError, match="not_found"):
        get_query_run(db_connection, caller=stranger, run_id=admitted.context.run_id)
    db_connection.execute("RESET ROLE")
