"""Durable admin notification helpers for ingestion anomalies."""

from __future__ import annotations

import json
import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from uuid import UUID

import psycopg

LOGGER = logging.getLogger(__name__)

DEFAULT_ADMIN_ALERT_SMTP_PORT = 54325


class AdminNotificationError(Exception):
    """Raised when admin notification persistence fails."""


def deliver_admin_alert_smtp(
    *,
    kind: str,
    severity: str,
    title: str,
    body: str,
    notification_id: UUID,
) -> None:
    """Best-effort SMTP copy of a durable admin notification (local Inbucket).

    SMTP failure is logged and never raised: the database row remains the
    source of truth.

    Args:
        kind: Notification kind already persisted.
        severity: ``info`` | ``warning`` | ``critical``.
        title: Operator-facing title without secrets.
        body: Safe diagnostic body.
        notification_id: Durable ``app.admin_notifications`` row id.

    Side Effects:
        Sends one SMTP message when ``ADMIN_ALERT_SMTP_HOST`` is set. Uses
        local Inbucket (``127.0.0.1:54325``) in development.
    """

    host = os.environ.get("ADMIN_ALERT_SMTP_HOST", "").strip()
    if not host:
        return
    port_raw = os.environ.get(
        "ADMIN_ALERT_SMTP_PORT", str(DEFAULT_ADMIN_ALERT_SMTP_PORT)
    )
    try:
        port = int(port_raw)
    except ValueError:
        LOGGER.warning("admin alert SMTP skipped: invalid ADMIN_ALERT_SMTP_PORT")
        return
    mail_from = os.environ.get("ADMIN_ALERT_SMTP_FROM", "alerts@localhost")
    mail_to = os.environ.get("ADMIN_ALERT_SMTP_TO", "owner@localhost")
    message = EmailMessage()
    message["From"] = mail_from
    message["To"] = mail_to
    message["Subject"] = f"[Smart RAG {severity}] {title}"
    message.set_content(
        f"kind={kind}\nseverity={severity}\nnotification_id={notification_id}\n\n{body}"
    )
    try:
        with smtplib.SMTP(host, port, timeout=5.0) as client:
            client.send_message(message)
    except OSError:
        LOGGER.warning(
            "admin alert SMTP delivery failed; durable row %s retained",
            notification_id,
            exc_info=True,
        )


@dataclass(frozen=True, slots=True)
class AdminNotificationRepository:
    """Worker/API repository for ``app.emit_admin_notification``."""

    connection: psycopg.Connection

    def emit(
        self,
        *,
        kind: str,
        severity: str,
        title: str,
        body: str,
        metadata: dict[str, object],
    ) -> UUID:
        """Append one durable admin notification row, then attempt SMTP.

        Args:
            kind: Notification kind (for example ``repeated_scan_failure``).
            severity: ``info`` | ``warning`` | ``critical``.
            title: Short operator-facing title without secrets.
            body: Safe diagnostic body.
            metadata: Structured metadata without raw content.

        Returns:
            Inserted notification id.

        Raises:
            AdminNotificationError: On database failures. SMTP errors are not
                raised.

        Side Effects:
            Inserts ``app.admin_notifications``. Optionally sends Inbucket SMTP.
        """

        try:
            row = self.connection.execute(
                """
                SELECT app.emit_admin_notification(%s, %s, %s, %s, %s::jsonb)
                """,
                (kind, severity, title, body, json.dumps(metadata)),
            ).fetchone()
        except psycopg.Error as exc:
            raise AdminNotificationError(str(exc)) from exc
        if row is None:
            raise AdminNotificationError("emit_admin_notification returned no row")
        notification_id = UUID(str(row[0]))
        deliver_admin_alert_smtp(
            kind=kind,
            severity=severity,
            title=title,
            body=body,
            notification_id=notification_id,
        )
        return notification_id
