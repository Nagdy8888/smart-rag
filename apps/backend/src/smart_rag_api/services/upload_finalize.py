"""Upload finalization after browser Storage upload completes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from smart_rag_api.services.upload_quota import (
    FinalizeUploadResult,
    finalize_upload_quota,
)


class UploadFinalizeError(Exception):
    """Raised when quarantine upload finalization fails closed."""


class DuplicateContentError(UploadFinalizeError):
    """Raised when the finalize content hash already belongs to a visible document."""


@dataclass(frozen=True, slots=True)
class UploadFinalizeRequest:
    """Server-side upload finalization inputs."""

    reservation_id: UUID
    object_name: str
    content_hash: str
    actual_bytes: int
    media_type: str | None
    declared_category: str
    attestation_policy_version: str
    idempotency_key: str
    document_title: str | None = None


@dataclass(frozen=True, slots=True)
class UploadFinalizeOutcome:
    """Durable document/version/job identifiers after finalization."""

    reservation_id: UUID
    quota: FinalizeUploadResult
    document_id: UUID
    version_id: UUID
    job_id: UUID


def _visible_document_id(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    content_hash: str,
) -> UUID | None:
    """Return a visible document that already stores this content hash.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role text.
        caller_authorization_version: Live authorization snapshot.
        content_hash: Lowercase SHA-256 hex of the uploaded bytes.

    Returns:
        Document id when the caller can read a non-deleted match.
        ``None`` when no visible document has this hash.

    Raises:
        UploadFinalizeError: When the lookup RPC fails.
    """

    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            row = connection.execute(
                """
                SELECT app.find_visible_document_by_content_hash(
                  %s::uuid, %s::text, %s::bigint, %s::text
                )
                """,
                (
                    caller_user_id,
                    caller_role,
                    caller_authorization_version,
                    content_hash,
                ),
            ).fetchone()
    except psycopg.Error as exc:
        raise UploadFinalizeError(str(exc)) from exc
    if row is None or row[0] is None:
        return None
    return UUID(str(row[0]))


def finalize_quarantine_upload(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    request: UploadFinalizeRequest,
) -> UploadFinalizeOutcome:
    """Finalize quota reservation and enqueue scan/promote ingestion job.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role text.
        caller_authorization_version: Live authorization snapshot.
        request: Verified object metadata and attestation fields.

    Returns:
        Quota finalize result plus created document/version/job ids.

    Raises:
        DuplicateContentError: When a non-deleted visible document already
            stores this content hash. Raised before quota is consumed.
        UploadFinalizeError: When quota, authorization, or RPC validation fails.

    Side Effects:
        Commits reservation finalize, creates document/version/job rows, appends
        audit event through SQL RPC. No write when the content hash is already
        visible.
    """

    existing = _visible_document_id(
        postgres_url,
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        content_hash=request.content_hash.lower(),
    )
    if existing is not None:
        raise DuplicateContentError("duplicate_content")

    quota = finalize_upload_quota(
        postgres_url,
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        reservation_id=request.reservation_id,
        actual_bytes=request.actual_bytes,
    )
    if quota.over_limit:
        raise UploadFinalizeError("upload exceeds declared or company quarantine cap")

    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT document_id, version_id, job_id
                    FROM app.finalize_quarantine_upload(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        caller_user_id,
                        caller_role,
                        caller_authorization_version,
                        request.reservation_id,
                        request.object_name,
                        request.content_hash.lower(),
                        request.actual_bytes,
                        request.media_type,
                        request.declared_category,
                        request.attestation_policy_version,
                        request.idempotency_key,
                        request.document_title,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
    except psycopg.Error as exc:
        raise UploadFinalizeError(str(exc)) from exc

    if row is None:
        raise UploadFinalizeError("finalize_quarantine_upload returned no row")

    return UploadFinalizeOutcome(
        reservation_id=request.reservation_id,
        quota=quota,
        document_id=row["document_id"],
        version_id=row["version_id"],
        job_id=row["job_id"],
    )
