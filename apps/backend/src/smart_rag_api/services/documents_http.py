"""Document list/detail and signed-upload/finalize HTTP wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.security.untrusted import isolate_untrusted_text

from smart_rag_api.services.keyset import parse_created_at_id_cursor
from smart_rag_api.services.upload_finalize import (
    DuplicateContentError,
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

_REASON_PREFIX = "documents:"


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """ACL-visible document summary."""

    document_id: UUID
    title: str | None
    visibility: str
    current_version_id: UUID | None
    visibility_generation: int
    created_at: datetime | None = None


class DocumentService:
    """Factory-injected document operations."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Postgres URL.
        """

        self._postgres_url = postgres_url

    def list(
        self,
        caller: CallerContext,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[DocumentRecord, ...]:
        """List documents the caller can read.

        Args:
            caller: Authenticated caller.
            limit: Page size, default 50, max 200.
            cursor: Optional ``created_at,id`` keyset cursor.

        Returns:
            Visible non-deleted documents, newest first.

        Raises:
            QueryAdmissionError: ``invalid_cursor`` or RPC rejection.
        """

        cursor_created_at, cursor_id = parse_created_at_id_cursor(cursor)
        capped = max(1, min(limit, 200))
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor(row_factory=dict_row) as cursor_obj:
                    cursor_obj.execute(
                        """
                        SELECT
                          id,
                          title,
                          visibility,
                          current_version_id,
                          visibility_generation,
                          created_at
                        FROM app.list_visible_documents_page(%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                            capped,
                            cursor_created_at,
                            cursor_id,
                        ),
                    )
                    rows = cursor_obj.fetchall()
        except psycopg.Error as exc:
            _raise_documents(exc)
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

        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """
                        SELECT id, title, visibility, current_version_id,
                               visibility_generation, created_at
                        FROM app.get_visible_document(
                          %s::uuid, %s::text, %s::bigint, %s::uuid
                        )
                        """,
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                            document_id,
                        ),
                    )
                    row = cursor.fetchone()
        except psycopg.Error as exc:
            _raise_documents(exc)
        if row is None:
            raise QueryAdmissionError("not_found")
        return _document_row(row)

    def delete(self, caller: CallerContext, *, document_id: UUID) -> None:
        """Tombstone one document through the canonical exclusion lifecycle.

        Args:
            caller: Authenticated caller. Owner/admin only.
            document_id: Document id.

        Raises:
            QueryAdmissionError: ``not_found`` when missing or unauthorized;
                ``forbidden`` when a visible document is not owner/admin-deletable.

        Side Effects:
            Calls ``app.delete_visible_document``, which wraps
            ``exclude_version_from_retrieval``, drops ``current_version_id``,
            and attaches Storage coordinates to BM25 delete jobs.
        """

        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT app.delete_visible_document(%s, %s, %s, %s)
                        """,
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                            document_id,
                        ),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg.Error as exc:
            _raise_documents(exc)
        if row is None or row[0] is None:
            raise QueryAdmissionError("not_found")

    def update_title(
        self,
        caller: CallerContext,
        *,
        document_id: UUID,
        title: str,
    ) -> DocumentRecord:
        """Rename one visible document. Owner/admin only.

        Args:
            caller: Authenticated caller.
            document_id: Document id.
            title: Already-trimmed title, 1-512 characters.

        Returns:
            The updated visible document.

        Raises:
            QueryAdmissionError: ``not_found`` when missing or unauthorized;
                ``forbidden`` when a visible document is not owner/admin;
                ``invalid_title`` when the RPC rejects the title.

        Side Effects:
            Calls ``app.update_document_title`` then reloads through
            ``app.get_visible_document``.
        """

        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT app.update_document_title(%s, %s, %s, %s, %s)
                        """,
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                            document_id,
                            title,
                        ),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg.Error as exc:
            _raise_documents(exc)
        if row is None or row[0] is None:
            raise QueryAdmissionError("not_found")
        return self.get(caller, document_id=document_id)

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
            DuplicateContentError: Visible document already has this hash.
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


def _raise_documents(exc: BaseException) -> NoReturn:
    """Map a Postgres error to a typed document failure.

    Args:
        exc: Driver or database error.

    Raises:
        QueryAdmissionError: Always, with a stable reason when prefixed.
    """

    message = str(exc)
    reason = "database_rejected"
    if _REASON_PREFIX in message:
        start = message.find(_REASON_PREFIX) + len(_REASON_PREFIX)
        tail = message[start:].split()[0].strip("\"'")
        reason = tail.split("\n")[0]
    raise QueryAdmissionError(reason) from exc


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
    created = mapped.get("created_at")
    created_at = created if isinstance(created, datetime) else None
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
        created_at=created_at,
    )


__all__ = [
    "DocumentRecord",
    "DocumentService",
    "DuplicateContentError",
    "UploadFinalizeError",
    "UploadQuotaError",
]
