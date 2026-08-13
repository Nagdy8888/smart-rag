"""Durable admin notification helpers for ingestion anomalies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

import psycopg


class AdminNotificationError(Exception):
    """Raised when admin notification persistence fails."""


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
        """Append one durable admin notification row.

        Args:
            kind: Notification kind (for example ``repeated_scan_failure``).
            severity: ``info`` | ``warning`` | ``critical``.
            title: Short operator-facing title without secrets.
            body: Safe diagnostic body.
            metadata: Structured metadata without raw content.

        Returns:
            Inserted notification id.

        Raises:
            AdminNotificationError: On database failures.
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
        return UUID(str(row[0]))
