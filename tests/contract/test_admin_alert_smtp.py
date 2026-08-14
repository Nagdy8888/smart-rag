"""Inbucket SMTP delivery for durable admin notifications."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from smart_rag_core.repositories.notifications import (
    AdminNotificationRepository,
    deliver_admin_alert_smtp,
)

from tests.contract.integration_support import (
    local_supabase_status,
    read_process_env,
    resolve_supabase_db_url,
    try_connect,
)
from tests.contract.test_local_auth_mail import _await_mail


@pytest.fixture
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield Postgres or skip when local Supabase is down."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        if read_process_env("SMART_RAG_REQUIRE_JOB_INTEGRATION") == "1":
            pytest.fail("Admin alert SMTP test requires reachable Supabase Postgres")
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.close()


def test_deliver_admin_alert_smtp_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SMTP transport failures are swallowed so the durable row remains."""

    monkeypatch.setenv("ADMIN_ALERT_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("ADMIN_ALERT_SMTP_PORT", "1")

    deliver_admin_alert_smtp(
        kind="repeated_scan_failure",
        severity="warning",
        title="smtp-fail",
        body="metadata only",
        notification_id=uuid.uuid4(),
    )


def test_anomaly_notification_creates_row_and_inbucket_mail(
    db_connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One anomaly fixture writes a DB row and a captured local SMTP message."""

    status = local_supabase_status()
    mailpit_url = status["MAILPIT_URL"]
    recipient = f"owner-alert-{uuid.uuid4()}@example.com"
    monkeypatch.setenv("ADMIN_ALERT_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("ADMIN_ALERT_SMTP_PORT", "54325")
    monkeypatch.setenv("ADMIN_ALERT_SMTP_FROM", "alerts@localhost")
    monkeypatch.setenv("ADMIN_ALERT_SMTP_TO", recipient)

    db_connection.execute("SET ROLE app_api")
    repository = AdminNotificationRepository(db_connection)
    note_id = repository.emit(
        kind="repeated_scan_failure",
        severity="warning",
        title="Anomaly fixture",
        body="metadata-only scan failure fixture",
        metadata={"fixture": True, "bytes": 12},
    )
    db_connection.commit()
    db_connection.execute("RESET ROLE")
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM app.admin_notifications WHERE id = %s",
            (note_id,),
        )
        row = cursor.fetchone()
        assert row is not None
    _await_mail(mailpit_url, recipient)
