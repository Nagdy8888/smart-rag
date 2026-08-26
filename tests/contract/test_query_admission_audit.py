"""Restricted-read audit, denied DML, and rate-limit admission."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr
from smart_rag_api.services.query_admission import admit_query_run_for_caller
from smart_rag_core.query_admission.exceptions import (
    QueryAdmissionError,
)
from smart_rag_core.query_admission.service import (
    record_run_restricted_evidence,
)
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.security.identity import UserRole

from tests.support.query_postgres import (
    admit as _admit,
)
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


def test_direct_audit_and_usage_dml_denied(
    db_connection: psycopg.Connection,
) -> None:
    """Runtime roles cannot insert/update/delete audit or usage rows."""

    with db_connection.cursor() as cursor:
        cursor.execute("SET ROLE app_api")
        cursor.execute("SAVEPOINT audit_ins")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                """
                INSERT INTO app.audit_events (event_type, payload)
                VALUES ('forged', '{"passage":"secret"}'::jsonb)
                """
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_ins")
        cursor.execute("SAVEPOINT usage_ins")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                """
                INSERT INTO app.llm_usage (
                  model_id, usage_kind, prompt_tokens, completion_tokens
                )
                VALUES ('x', 'answer', 1, 1)
                """
            )
        cursor.execute("ROLLBACK TO SAVEPOINT usage_ins")
        cursor.execute("SAVEPOINT restricted_ins")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute(
                "INSERT INTO app.restricted_read_events (purpose) VALUES ('evidence')"
            )
        cursor.execute("ROLLBACK TO SAVEPOINT restricted_ins")
        cursor.execute("RESET ROLE")
        usage_id = cursor.execute(
            """
            INSERT INTO app.llm_usage (model_id, usage_kind)
            VALUES ('fixture', 'answer')
            RETURNING id
            """
        ).fetchone()
        assert usage_id is not None
        cursor.execute("SAVEPOINT usage_update")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cursor.execute(
                "UPDATE app.llm_usage SET cost_usd = 9 WHERE id = %s",
                (usage_id[0],),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT usage_update")
        cursor.execute("SAVEPOINT usage_delete")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cursor.execute("DELETE FROM app.llm_usage WHERE id = %s", (usage_id[0],))
        cursor.execute("ROLLBACK TO SAVEPOINT usage_delete")
        audit_id = cursor.execute(
            """
            INSERT INTO app.audit_events (event_type)
            VALUES ('fixture')
            RETURNING id
            """
        ).fetchone()
        assert audit_id is not None
        cursor.execute("SAVEPOINT audit_update")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cursor.execute(
                "UPDATE app.audit_events SET event_type = 'x' WHERE id = %s",
                (audit_id[0],),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_update")
        cursor.execute("SAVEPOINT audit_delete")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cursor.execute(
                "DELETE FROM app.audit_events WHERE id = %s",
                (audit_id[0],),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_delete")


def test_restricted_run_evidence_is_chained_and_content_minimized(
    db_connection: psycopg.Connection,
) -> None:
    """Run-completion restricted evidence stores ids only, never passage text."""

    owner_id = uuid4()
    member_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=owner_id, role="owner")
        _insert_user_profile(cursor, user_id=member_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=member_id)
        cursor.execute(
            """
            INSERT INTO app.documents (
              id, title, visibility, created_by, graph_eligible
            )
            VALUES (%s, 'Restricted run evidence', 'restricted', %s, false)
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
            "UPDATE app.documents SET current_version_id = %s WHERE id = %s",
            (version_id, document_id),
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
        authz = _authorization_version(cursor)
    caller = _caller(member_id, "member", authz)
    admitted, _ = _admit(
        db_connection,
        caller=caller,
        conversation_id=conversation_id,
    )
    with db_connection.cursor() as cursor:
        citation_id = cursor.execute(
            """
            INSERT INTO app.citations (run_id, citation_index, snippet, provenance)
            VALUES (%s, 0, 'should not be copied into audit', '{}'::jsonb)
            RETURNING id
            """,
            (admitted.context.run_id,),
        ).fetchone()
        assert citation_id is not None
    db_connection.execute("SET ROLE app_api")
    event_id = record_run_restricted_evidence(
        db_connection,
        caller=caller,
        run_id=admitted.context.run_id,
        document_id=document_id,
        version_id=version_id,
        session_id="session-run-evidence",
        citation_id=citation_id[0],
        purpose="evidence",
    )
    db_connection.execute("RESET ROLE")
    with db_connection.cursor() as cursor:
        row = cursor.execute(
            """
            SELECT
              restricted.purpose,
              restricted.run_id,
              restricted.citation_id,
              audit.payload,
              audit.event_type,
              audit.session_id
            FROM app.restricted_read_events AS restricted
            JOIN app.audit_events AS audit
              ON audit.id = restricted.audit_event_id
            WHERE restricted.id = %s
            """,
            (event_id,),
        ).fetchone()
        chain = cursor.execute("SELECT app.verify_audit_chain(1000)").fetchone()
    assert row is not None
    assert row[0] == "evidence"
    assert row[1] == admitted.context.run_id
    assert row[2] == citation_id[0]
    payload = row[3]
    assert payload["run_id"] == str(admitted.context.run_id)
    assert payload["citation_id"] == str(citation_id[0])
    assert payload["version_id"] == str(version_id)
    assert "should not be copied" not in str(payload)
    assert "passage" not in payload
    assert row[4] == "restricted_read.authorized"
    assert row[5] == "session-run-evidence"
    assert chain == (None,)


def test_fastapi_rate_limit_reject_creates_no_reservation(
    db_url: str,
    db_connection: psycopg.Connection,
) -> None:
    """429 and limiter-unavailable fail before cost; Valkey cannot authorize."""

    user_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=user_id, role="member")
        conversation_id = _insert_conversation(cursor, user_id=user_id)
        version = _authorization_version(cursor)
    db_connection.commit()
    caller = _caller(user_id, "member", version)
    with pytest.raises(QueryAdmissionError, match="limiter_unavailable"):
        admit_query_run_for_caller(
            db_url,
            caller=caller,
            conversation_id=conversation_id,
            idempotency_key=uuid4(),
            message="limited",
            route_family=Phase6RouteFamily.HYBRID,
            postgres_rate_limit_url=SecretStr("postgresql://x:y@127.0.0.1:1/none"),
        )
    with db_connection.cursor() as cursor:
        before = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.budget_reservations
            WHERE user_id = %s AND reservation_kind = 'query_run'
            """,
            (user_id,),
        ).fetchone()
    assert before == (0,)

    from smart_rag_api.services.auth_rate_limits import check_auth_rate_limit
    from smart_rag_api.services.query_admission import query_admission_bucket_key

    bucket = query_admission_bucket_key(str(user_id))
    postgres = SecretStr(db_url)
    for _ in range(20):
        check_auth_rate_limit(
            bucket_key=bucket,
            max_attempts=20,
            window_seconds=60,
            postgres_url=postgres,
        )
    with pytest.raises(QueryAdmissionError, match="rate_limited"):
        admit_query_run_for_caller(
            db_url,
            caller=caller,
            conversation_id=conversation_id,
            idempotency_key=uuid4(),
            message="limited",
            route_family=Phase6RouteFamily.HYBRID,
        )
    with db_connection.cursor() as cursor:
        after = cursor.execute(
            """
            SELECT count(*)::integer
            FROM app.budget_reservations
            WHERE user_id = %s AND reservation_kind = 'query_run'
            """,
            (user_id,),
        ).fetchone()
    assert after == (0,)

    other_id = uuid4()
    with db_connection.cursor() as cursor:
        _insert_user_profile(cursor, user_id=other_id, role="member")
        other_conv = _insert_conversation(cursor, user_id=other_id)
        other_version = _authorization_version(cursor)
    db_connection.commit()
    other_caller = _caller(other_id, "member", other_version)
    result = admit_query_run_for_caller(
        db_url,
        caller=other_caller,
        conversation_id=other_conv,
        idempotency_key=uuid4(),
        message="ok-after-new-bucket-user",
        route_family=Phase6RouteFamily.HYBRID,
        postgres_rate_limit_url=SecretStr(db_url),
        valkey_limits_url=SecretStr("redis://valkey-is-not-authority"),
    )
    assert result.reconnect is False
    assert result.context.reserved_amount_usd == Decimal("2.80")
    assert result.context.role is UserRole.MEMBER
    _retire_committed_query_run(
        db_url,
        run_id=result.context.run_id,
        reservation_id=result.context.reservation_id,
    )
