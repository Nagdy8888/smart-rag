"""Document list/detail and signed-upload/finalize HTTP wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.security.untrusted import isolate_untrusted_text

from smart_rag_api.services.upload_finalize import (
    UploadFinalizeError,
    UploadFinalizeOutcome,
    UploadFinalizeRequest,
    finalize_quarantine_upload,
)
from smart_rag_api.services.upload_quota import (
    UploadQuotaError,
    UploadReservation,
    reserve_upload_quota,
)


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """ACL-visible document summary."""

    document_id: UUID
    title: str | None
    visibility: str
    current_version_id: UUID | None
    visibility_generation: int


class DocumentService:
    """Factory-injected document operations."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Postgres URL.
        """

        self._postgres_url = postgres_url

    def list(self, caller: CallerContext) -> tuple[DocumentRecord, ...]:
        """List documents the caller can read.

        Args:
            caller: Authenticated caller.

        Returns:
            Visible non-deleted documents.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT id, title, visibility, current_version_id, visibility_generation
                    FROM app.list_visible_documents(%s, %s, %s)
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                    ),
                )
                rows = cursor.fetchall()
        return tuple(_document_row(row) for row in rows)

    def get(self, caller: CallerContext, *, document_id: UUID) -> DocumentRecord:
        """Load one visible document.

        Args:
            caller: Authenticated caller.
            document_id: Document id.

        Returns:
            Document record.

        Raises:
            QueryAdmissionError: ``not_found`` when missing or unauthorized.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT id, title, visibility, current_version_id, visibility_generation
                    FROM app.get_visible_document(%s, %s, %s, %s)
                    """,
                    (
                        caller.user_id,
                        caller.rpc_role(),
                        caller.rpc_authorization_version(),
                        document_id,
                    ),
                )
                row = cursor.fetchone()
        if row is None:
            raise QueryAdmissionError("not_found")
        return _document_row(row)

    def reserve_upload(
        self,
        caller: CallerContext,
        *,
        declared_bytes: int,
        idempotency_key: str,
        access_token_exp: datetime | None = None,
    ) -> UploadReservation:
        """Reserve quarantine upload quota after role/capability checks.

        Args:
            caller: Authenticated caller.
            declared_bytes: Declared object size.
            idempotency_key: Client idempotency key.
            access_token_exp: Optional JWT exp.

        Returns:
            Reservation including storage path. Local uploads use the user JWT
            to the quarantine path; CloudFront signed URLs are Phase 10.

        Raises:
            QueryAdmissionError: Viewers or callers without upload capability.
            UploadQuotaError: Quota RPC failure.
        """

        if caller.role is UserRole.VIEWER or not caller.upload_enabled:
            raise QueryAdmissionError("forbidden")
        return reserve_upload_quota(
            self._postgres_url,
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.rpc_role(),
            caller_authorization_version=caller.rpc_authorization_version(),
            declared_bytes=declared_bytes,
            idempotency_key=idempotency_key,
            session_id=caller.session_id,
            access_token_exp=access_token_exp,
        )

    def finalize_upload(
        self,
        caller: CallerContext,
        *,
        request: UploadFinalizeRequest,
    ) -> UploadFinalizeOutcome:
        """Finalize a reserved upload.

        Args:
            caller: Authenticated caller.
            request: Finalize payload.

        Returns:
            Document/version/job identifiers.

        Raises:
            QueryAdmissionError: Viewers or callers without upload capability.
            UploadFinalizeError: Finalize RPC failure.
        """

        if caller.role is UserRole.VIEWER or not caller.upload_enabled:
            raise QueryAdmissionError("forbidden")
        return finalize_quarantine_upload(
            self._postgres_url,
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.rpc_role(),
            caller_authorization_version=caller.rpc_authorization_version(),
            request=request,
        )


def _as_int(value: object) -> int:
    """Convert a SQL scalar to int.

    Args:
        value: Row value.

    Returns:
        Integer generation or count.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        return int(str(value))
    return value


def _document_row(row: object) -> DocumentRecord:
    """Map one SQL row to a document record.

    Args:
        row: RPC row.

    Returns:
        Escaped document record.

    Raises:
        QueryAdmissionError: When the row is not a mapping.
    """

    if not isinstance(row, dict):
        raise QueryAdmissionError("not_found")
    mapped = cast(dict[str, object], row)
    raw_title = mapped.get("title")
    return DocumentRecord(
        document_id=UUID(str(mapped["id"])),
        title=isolate_untrusted_text(str(raw_title)) if raw_title is not None else None,
        visibility=str(mapped["visibility"]),
        current_version_id=(
            UUID(str(mapped["current_version_id"]))
            if mapped.get("current_version_id") is not None
            else None
        ),
        visibility_generation=_as_int(mapped["visibility_generation"]),
    )


__all__ = [
    "DocumentRecord",
    "DocumentService",
    "UploadFinalizeError",
    "UploadQuotaError",
]
