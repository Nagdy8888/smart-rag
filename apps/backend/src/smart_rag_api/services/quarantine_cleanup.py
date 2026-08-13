"""Quarantine cleanup orchestration using Storage API + durable quota rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_api.storage_admin.objects import StorageAdminError, delete_object
from smart_rag_api.storage_admin.settings import PrivilegedStorageSettings


class QuarantineCleanupError(Exception):
    """Raised when cleanup candidate processing fails unsafely."""


@dataclass(frozen=True, slots=True)
class CleanupCandidate:
    """One quarantine object requiring Storage API deletion."""

    reservation_id: UUID
    user_id: UUID
    storage_bucket: str
    storage_path: str | None
    reserved_bytes: int
    actual_bytes: int | None
    cleanup_status: str | None
    reason: str


def list_cleanup_candidates(
    postgres_url: str,
    *,
    as_of: datetime | None = None,
    limit: int = 100,
) -> list[CleanupCandidate]:
    """List never-finalized or over-limit quarantine cleanup candidates.

    Args:
        postgres_url: Database URL; uses ``SET ROLE app_worker``.
        as_of: Controllable clock for TTL evaluation.
        limit: Maximum rows (1-1000).

    Returns:
        Bounded candidate list.

    Raises:
        QuarantineCleanupError: On database failures.
    """

    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_worker")
            with connection.cursor(row_factory=dict_row) as cursor:
                if as_of is None:
                    cursor.execute(
                        """
                        SELECT * FROM app.list_quarantine_cleanup_candidates(
                          timezone('utc', now()), %s
                        )
                        """,
                        (limit,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM app.list_quarantine_cleanup_candidates(%s, %s)
                        """,
                        (as_of, limit),
                    )
                rows = cursor.fetchall()
            connection.commit()
    except psycopg.Error as exc:
        raise QuarantineCleanupError(str(exc)) from exc

    return [
        CleanupCandidate(
            reservation_id=row["reservation_id"],
            user_id=row["user_id"],
            storage_bucket=row["storage_bucket"],
            storage_path=row["storage_path"],
            reserved_bytes=int(row["reserved_bytes"]),
            actual_bytes=(
                int(row["actual_bytes"]) if row["actual_bytes"] is not None else None
            ),
            cleanup_status=row["cleanup_status"],
            reason=row["reason"],
        )
        for row in rows
    ]


def process_cleanup_candidate(
    postgres_url: str,
    settings: PrivilegedStorageSettings,
    candidate: CleanupCandidate,
    *,
    object_name: str | None = None,
) -> None:
    """Delete provider bytes via Storage API then mark quota cleanup done.

    Args:
        postgres_url: Database URL for reconciliation RPC.
        settings: Privileged Storage Admin settings.
        candidate: Cleanup candidate row.
        object_name: Exact object key when known; otherwise ``storage_path``.

    Raises:
        QuarantineCleanupError: When Storage delete or reconciliation fails.
        ValueError: When no object path is available.

    Side Effects:
        Calls Storage HTTP DELETE (not SQL delete of ``storage.objects``).
        Marks reservation cleanup done idempotently. Safe to retry.
    """

    path = (object_name or candidate.storage_path or "").lstrip("/")
    if not path:
        raise ValueError("cleanup candidate missing storage path")

    # If path is a prefix ending with /, worker must pass concrete object_name.
    if path.endswith("/"):
        raise ValueError("object_name required when storage_path is a prefix")

    try:
        delete_object(
            settings,
            bucket=candidate.storage_bucket,
            object_path=path,
        )
    except StorageAdminError as exc:
        raise QuarantineCleanupError(str(exc)) from exc

    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_worker")
            connection.execute(
                "SELECT app.mark_quarantine_cleanup_done(%s)",
                (candidate.reservation_id,),
            )
            connection.commit()
    except psycopg.Error as exc:
        raise QuarantineCleanupError(str(exc)) from exc
