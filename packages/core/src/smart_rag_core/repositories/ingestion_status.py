"""Ingestion lifecycle status queries for public APIs."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class IngestionStatusRepository:
    """Read ingestion lifecycle through the ACL status RPC."""

    def __init__(self, connection: psycopg.Connection) -> None:
        """Bind one API Postgres connection for status reads.

        Args:
            connection: Open connection; callers set ``app_api``.
        """

        self._connection = connection

    def get_version_status(
        self,
        version_id: UUID,
        *,
        caller_user_id: str,
        caller_role: str,
        caller_authorization_version: int,
    ) -> dict[str, Any] | None:
        """Return public lifecycle plus nested diagnostics when authorized.

        Args:
            version_id: Canonical document version identifier.
            caller_user_id: Server-derived subject UUID string.
            caller_role: Server-derived ``app.user_role`` text.
            caller_authorization_version: Live company authorization snapshot.

        Returns:
            Row dict matching ``IngestionStatusResponse`` field names plus
            ``recent_jobs``, or ``None`` when the version is missing or
            unauthorized. Does not leak existence to unauthorized callers.
        """

        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT status_payload, recent_jobs
                FROM app.get_version_ingestion_status(
                  %s::uuid, %s::text, %s::bigint, %s::uuid
                )
                """,
                (
                    caller_user_id,
                    caller_role,
                    caller_authorization_version,
                    version_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            payload: object = row.get("status_payload")
            if not isinstance(payload, dict):
                return None
            result = cast(dict[str, Any], payload)
            jobs: object = row.get("recent_jobs") or []
            result["recent_jobs"] = jobs if isinstance(jobs, list) else []
            review = result.get("review")
            if not isinstance(review, dict):
                return result
            try:
                cursor.execute(
                    """
                    SELECT app.version_governance_review_diagnostics(
                      %s::uuid, %s::text, %s::bigint, %s::uuid
                    ) AS diagnostics
                    """,
                    (
                        caller_user_id,
                        caller_role,
                        caller_authorization_version,
                        version_id,
                    ),
                )
                diagnostics = cursor.fetchone()
            except psycopg.Error:
                return result
            extra: object = (
                None if diagnostics is None else diagnostics.get("diagnostics")
            )
            if isinstance(extra, dict):
                review_map = cast(dict[str, object], review)
                extra_map = cast(dict[str, object], extra)
                result["review"] = {**review_map, **extra_map}
            return result
