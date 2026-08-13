"""Append-only audit hash-chain contract tests (Phase 2 Packet 6)."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from smart_rag_core.security.audit_chain import (
    AUDIT_CHAIN_GENESIS_HASH,
    redact_audit_payload,
)

from tests.contract.integration_support import resolve_supabase_db_url, try_connect


@pytest.fixture
def db_connection() -> psycopg.Connection:
    """Yield one Postgres connection or skip when Supabase is unreachable."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_redact_audit_payload_strips_sensitive_keys() -> None:
    """Python redaction helper matches Packet 6 sensitive-key policy."""

    marker = "[REDACTED]"
    redacted = redact_audit_payload(
        {
            "ok": True,
            "password": "plain",
            "refresh_token": "abc",
            "api_secret": "x",
            "client_raw_ip": "1.2.3.4",
            "nested": {"access_token": "jwt", "path": "/a"},
        }
    )
    assert redacted["ok"] is True
    assert redacted["password"] == marker
    assert redacted["refresh_token"] == marker
    assert redacted["api_secret"] == marker
    assert redacted["client_raw_ip"] == marker
    assert redacted["nested"]["access_token"] == marker
    assert redacted["nested"]["path"] == "/a"
    assert len(AUDIT_CHAIN_GENESIS_HASH) == 64


def test_append_chain_redaction_and_immutability(
    db_connection: psycopg.Connection,
) -> None:
    """Append events, redact secrets, block UPDATE/DELETE, detect tamper."""

    marker = "[REDACTED]"
    actor = uuid.uuid4()
    with db_connection.cursor() as cursor:
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
            (actor, f"{actor}@example.com"),
        )
        cursor.execute(
            """
            INSERT INTO app.profiles (user_id, role, display_name)
            VALUES (%s, 'admin', 'Audit Tester')
            ON CONFLICT (user_id) DO NOTHING
            """,
            (actor,),
        )
        cursor.execute("SELECT app.current_authorization_version()")
        auth_version = int(cursor.fetchone()[0])

        cursor.execute("SET ROLE app_audit_writer")
        cursor.execute(
            """
            SELECT app.append_audit_event(
              'packet6_chain_a',
              %s,
              'admin'::app.user_role,
              'test',
              %s,
              %s,
              '{"password":"secret","note":"ok"}'::jsonb,
              'unit-test',
              'fixture',
              %s,
              'sess-1'
            )
            """,
            (actor, actor, auth_version, actor),
        )
        first_id = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT app.append_audit_event(
              'packet6_chain_b',
              %s,
              'admin'::app.user_role,
              'test',
              %s,
              %s,
              '{"token":"abc"}'::jsonb
            )
            """,
            (actor, actor, auth_version),
        )
        second_id = cursor.fetchone()[0]

        cursor.execute("RESET ROLE")
        cursor.execute(
            """
            SELECT event_hash, previous_hash, payload
            FROM app.audit_events
            WHERE id = %s
            """,
            (first_id,),
        )
        first_hash, first_prev, first_payload = cursor.fetchone()
        assert first_prev == AUDIT_CHAIN_GENESIS_HASH
        assert first_hash and len(first_hash) == 64
        assert first_payload["password"] == marker
        assert first_payload["note"] == "ok"

        cursor.execute(
            """
            SELECT previous_hash, payload
            FROM app.audit_events
            WHERE id = %s
            """,
            (second_id,),
        )
        second_prev, second_payload = cursor.fetchone()
        assert second_prev == first_hash
        assert second_payload["token"] == marker

        cursor.execute("SELECT app.verify_audit_chain(100)")
        assert cursor.fetchone()[0] is None

        cursor.execute("SET ROLE app_audit_writer")
        with pytest.raises(
            (psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)
        ):
            cursor.execute("SAVEPOINT audit_upd")
            cursor.execute(
                "UPDATE app.audit_events SET event_type = 'mutated' WHERE id = %s",
                (first_id,),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_upd")
        cursor.execute("RELEASE SAVEPOINT audit_upd")

        with pytest.raises(
            (psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)
        ):
            cursor.execute("SAVEPOINT audit_del")
            cursor.execute(
                "DELETE FROM app.audit_events WHERE id = %s",
                (second_id,),
            )
        cursor.execute("ROLLBACK TO SAVEPOINT audit_del")
        cursor.execute("RELEASE SAVEPOINT audit_del")
        cursor.execute("RESET ROLE")

        # Superuser tamper path: disable user triggers, mutate hash, re-enable.
        cursor.execute("ALTER TABLE app.audit_events DISABLE TRIGGER USER")
        cursor.execute(
            "UPDATE app.audit_events SET event_hash = 'deadbeef' WHERE id = %s",
            (second_id,),
        )
        cursor.execute("ALTER TABLE app.audit_events ENABLE TRIGGER USER")
        cursor.execute("SELECT app.verify_audit_chain(100)")
        broken_at = cursor.fetchone()[0]
        assert broken_at == second_id


def test_verify_detects_reordered_previous_hash(
    db_connection: psycopg.Connection,
) -> None:
    """Reordered previous_hash links fail ``verify_audit_chain``."""

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT app.append_audit_event(
              'packet6_reorder_a',
              NULL,
              NULL,
              'test',
              NULL,
              NULL,
              '{}'::jsonb
            )
            """
        )
        # append as security definer via postgres (superuser) is fine
        first_id = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT app.append_audit_event(
              'packet6_reorder_b',
              NULL,
              NULL,
              'test',
              NULL,
              NULL,
              '{}'::jsonb
            )
            """
        )
        second_id = cursor.fetchone()[0]
        cursor.execute(
            "SELECT event_hash FROM app.audit_events WHERE id = %s",
            (first_id,),
        )
        first_hash = cursor.fetchone()[0]

        cursor.execute("ALTER TABLE app.audit_events DISABLE TRIGGER USER")
        cursor.execute(
            """
            UPDATE app.audit_events
            SET previous_hash = %s, event_hash = 'cafebabe'
            WHERE id = %s
            """,
            (AUDIT_CHAIN_GENESIS_HASH, second_id),
        )
        # Force a break relative to first event link without matching digest.
        cursor.execute(
            """
            UPDATE app.audit_events
            SET previous_hash = %s
            WHERE id = %s
            """,
            ("f" * 64, second_id),
        )
        cursor.execute("ALTER TABLE app.audit_events ENABLE TRIGGER USER")

        cursor.execute("SELECT app.verify_audit_chain(100)")
        broken_at = cursor.fetchone()[0]
        assert broken_at == second_id
        assert first_hash
