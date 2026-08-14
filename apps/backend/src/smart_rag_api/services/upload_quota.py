"""Upload quota admission helpers using the ``app_api`` database role."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class UploadQuotaError(Exception):
    """Raised when reserve/finalize quota RPCs fail closed."""


@dataclass(frozen=True, slots=True)
class UploadReservation:
    """Durable quarantine upload admission result.

    Attributes:
        reservation_id: Quota reservation primary key.
        expires_at: Provisional 15-minute admission expiry (UTC).
        reserved_bytes: Declared bytes held against per-user/company caps.
        storage_bucket: Always ``documents-quarantine`` for browser uploads.
        storage_path: Prefix ``{user_id}/{reservation_id}/``.
        access_token_exp: Optional JWT ``exp`` for truthful capability labeling.
        document_id: Document shell created at reserve (Uploading).
        version_id: Version created at reserve as ``uploading``.
    """

    reservation_id: UUID
    expires_at: datetime
    reserved_bytes: int
    storage_bucket: str
    storage_path: str
    access_token_exp: datetime | None = None
    document_id: UUID | None = None
    version_id: UUID | None = None

    @property
    def effective_capability_expires_at(self) -> datetime:
        """Return ``min(reservation_expires_at, access_token_exp)`` when known.

        The 15-minute reservation does **not** revoke a longer-lived JWT. Callers
        must label effective upload capability as the minimum of both clocks.
        """

        if self.access_token_exp is None:
            return self.expires_at
        return min(self.expires_at, self.access_token_exp)


@dataclass(frozen=True, slots=True)
class FinalizeUploadResult:
    """Result of comparing actual Storage bytes to the reservation."""

    reservation_id: UUID
    status: str
    cleanup_status: str | None
    reserved_bytes: int
    actual_bytes: int
    over_limit: bool


def reserve_upload_quota(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    declared_bytes: int,
    idempotency_key: str,
    session_id: str | None,
    access_token_exp: datetime | None = None,
    storage_path: str | None = None,
) -> UploadReservation:
    """Reserve declared upload bytes through ``app.reserve_upload_quota``.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role text.
        caller_authorization_version: Live authorization snapshot.
        declared_bytes: Advisory declared size before upload.
        idempotency_key: Stable client key for replay-safe admission.
        session_id: Auth session id bound to the reservation.
        access_token_exp: JWT expiry used only for capability labeling.
        storage_path: Optional explicit quarantine path override.

    Returns:
        ``UploadReservation`` including truthful effective capability helper.

    Raises:
        UploadQuotaError: When the RPC rejects authorization or quotas.

    Side Effects:
        Inserts or returns an existing ``app.upload_quota_reservations`` row.
        Uses role ``app_api`` for EXECUTE grants.
    """

    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM app.reserve_upload_quota(
                      %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        caller_user_id,
                        caller_role,
                        caller_authorization_version,
                        declared_bytes,
                        idempotency_key,
                        session_id,
                        storage_path,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
    except psycopg.Error as exc:
        raise UploadQuotaError(str(exc)) from exc

    if row is None:
        raise UploadQuotaError("reserve_upload_quota returned no row")

    return UploadReservation(
        reservation_id=row["reservation_id"],
        expires_at=row["expires_at"],
        reserved_bytes=int(row["reserved_bytes"]),
        storage_bucket=row["storage_bucket"],
        storage_path=row["reserved_storage_path"],
        access_token_exp=access_token_exp,
        document_id=row.get("document_id"),
        version_id=row.get("version_id"),
    )


def finalize_upload_quota(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    reservation_id: UUID,
    actual_bytes: int,
) -> FinalizeUploadResult:
    """Finalize a reservation after Storage reports actual object size.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role text.
        caller_authorization_version: Live authorization snapshot.
        reservation_id: Reservation to finalize.
        actual_bytes: Provider-reported object size.

    Returns:
        ``FinalizeUploadResult`` including over-limit cleanup marking.

    Raises:
        UploadQuotaError: When ownership/authorization fails.

    Side Effects:
        Updates reservation rows; may emit admin notifications for over-limit.
        Idempotent on already-finalized reservations.
    """

    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM app.finalize_upload_quota(%s, %s, %s, %s, %s)
                    """,
                    (
                        caller_user_id,
                        caller_role,
                        caller_authorization_version,
                        reservation_id,
                        actual_bytes,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
    except psycopg.Error as exc:
        raise UploadQuotaError(str(exc)) from exc

    if row is None:
        raise UploadQuotaError("finalize_upload_quota returned no row")

    return FinalizeUploadResult(
        reservation_id=row["reservation_id"],
        status=str(row["status"]),
        cleanup_status=row["cleanup_status"],
        reserved_bytes=int(row["reserved_bytes"]),
        actual_bytes=int(row["recorded_actual_bytes"]),
        over_limit=bool(row["over_limit"]),
    )
