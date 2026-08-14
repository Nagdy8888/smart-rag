"""Owner/admin glossary import service over security-definer RPCs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from smart_rag_core.glossary.models import GlossaryBatch, GlossaryImportStatus
from smart_rag_core.glossary.validation import (
    validate_glossary_batch,
)

LOGGER = logging.getLogger(__name__)


class GlossaryImportRejectedError(RuntimeError):
    """Raised when SQL or validation rejects a glossary mutation."""

    def __init__(self, reason: str) -> None:
        """Initialize with a reason code and no private glossary text.

        Args:
            reason: Stable reason such as ``forbidden`` or ``alias_cycle``.
        """

        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class GlossaryImportOutcome:
    """Durable identifiers after import, approval, or rollback.

    Attributes:
        import_id: Glossary import row id.
        status: Lifecycle status.
        entry_count: Canonical entries in the batch.
        alias_count: Aliases in the batch.
    """

    import_id: UUID
    status: GlossaryImportStatus
    entry_count: int
    alias_count: int


def _reason_from_db(exc: psycopg.Error) -> str:
    """Map a database error to a reason code without copying SQL detail.

    Args:
        exc: Driver error. Diagnostic text is not returned to callers or logs.

    Returns:
        Stable reason code.
    """

    message = str(exc).lower()
    for code in (
        "forbidden",
        "alias_cycle",
        "alias_conflict",
        "duplicate_alias",
        "cross_scope_conflict",
        "canonical_missing",
        "high_collision_rule",
        "unapproved_import",
        "already_approved",
        "already_rolled_back",
        "import_not_found",
    ):
        if code in message:
            return code
    return "glossary_rejected"


def import_glossary_batch(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    batch: GlossaryBatch,
) -> GlossaryImportOutcome:
    """Validate and persist a pending glossary import.

    Unapproved rows never populate ``search_aliases``. Logs record import id
    and counts only.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        batch: Typed import payload.

    Returns:
        Import identifiers. Duplicate idempotency keys reuse one row.

    Raises:
        GlossaryValidationError: If the batch fails closed locally.
        GlossaryImportRejectedError: If the RPC rejects the caller or payload.

    Side Effects:
        Inserts pending glossary rows and an append-only audit event.
    """

    validate_glossary_batch(batch)
    payload = {
        "entries": [
            {
                "entry_key": entry.entry_key,
                "canonical_term": entry.canonical_term,
                "language": entry.language.value,
                "entry_type": entry.entry_type.value,
                "effective_scope": entry.effective_scope.value,
                "identifier_pattern": entry.identifier_pattern,
                "checksum_algorithm": entry.checksum_algorithm,
                "aliases": [
                    {"alias": alias.alias, "language": alias.language.value}
                    for alias in entry.aliases
                ],
            }
            for entry in batch.entries
        ]
    }
    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM app.import_glossary_batch(
                      %s::uuid,
                      %s::text,
                      %s::bigint,
                      %s::text,
                      %s::text,
                      %s::text,
                      %s::jsonb
                    )
                    """,
                    (
                        caller_user_id,
                        caller_role,
                        caller_authorization_version,
                        batch.source_name,
                        batch.source_version,
                        batch.idempotency_key,
                        Json(payload),
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
    except psycopg.Error as exc:
        LOGGER.info(
            "glossary import rejected",
            extra={"event": "glossary.import.rejected", "reason": _reason_from_db(exc)},
        )
        raise GlossaryImportRejectedError(_reason_from_db(exc)) from exc
    if row is None:
        raise GlossaryImportRejectedError("glossary_rejected")
    outcome = GlossaryImportOutcome(
        import_id=UUID(str(row["import_id"])),
        status=GlossaryImportStatus(str(row["status"])),
        entry_count=int(row["entry_count"]),
        alias_count=int(row["alias_count"]),
    )
    LOGGER.info(
        "glossary import persisted",
        extra={
            "event": "glossary.import.persisted",
            "import_id": str(outcome.import_id),
            "status": outcome.status.value,
            "entry_count": outcome.entry_count,
            "alias_count": outcome.alias_count,
        },
    )
    return outcome


def approve_glossary_import(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    import_id: UUID,
) -> GlossaryImportOutcome:
    """Approve a pending import and project aliases into search_aliases.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        import_id: Pending import identifier.

    Returns:
        Updated import outcome.

    Raises:
        GlossaryImportRejectedError: If the caller is unauthorized or the
            import is not pending.

    Side Effects:
        Writes approved ``search_aliases`` rows and an audit event.
    """

    return _mutate_import(
        postgres_url,
        function_name="approve_glossary_import",
        event="glossary.import.approved",
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        import_id=import_id,
    )


def rollback_glossary_import(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    import_id: UUID,
) -> GlossaryImportOutcome:
    """Roll back an approved import by deleting its search_aliases projection.

    Args:
        postgres_url: Database URL used with ``SET ROLE app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        import_id: Approved import identifier.

    Returns:
        Updated import outcome.

    Raises:
        GlossaryImportRejectedError: If the caller is unauthorized or rollback
            is not allowed.

    Side Effects:
        Deletes projected aliases for the import and appends an audit event.
    """

    return _mutate_import(
        postgres_url,
        function_name="rollback_glossary_import",
        event="glossary.import.rolled_back",
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        import_id=import_id,
    )


def _mutate_import(
    postgres_url: str,
    *,
    function_name: str,
    event: str,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    import_id: UUID,
) -> GlossaryImportOutcome:
    """Invoke an approve or rollback RPC.

    Args:
        postgres_url: Database URL.
        function_name: Allow-listed function name.
        event: Structured log event name.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        import_id: Target import.

    Returns:
        Updated outcome.

    Raises:
        GlossaryImportRejectedError: If the RPC fails or returns no row.
    """

    if function_name == "approve_glossary_import":
        sql = (
            "SELECT * FROM app.approve_glossary_import("
            "%s::uuid, %s::text, %s::bigint, %s::uuid)"
        )
    elif function_name == "rollback_glossary_import":
        sql = (
            "SELECT * FROM app.rollback_glossary_import("
            "%s::uuid, %s::text, %s::bigint, %s::uuid)"
        )
    else:
        raise GlossaryImportRejectedError("glossary_rejected")
    try:
        with psycopg.connect(postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    sql,
                    (
                        caller_user_id,
                        caller_role,
                        caller_authorization_version,
                        import_id,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
    except psycopg.Error as exc:
        LOGGER.info(
            "glossary mutation rejected",
            extra={"event": f"{event}.rejected", "reason": _reason_from_db(exc)},
        )
        raise GlossaryImportRejectedError(_reason_from_db(exc)) from exc
    if row is None:
        raise GlossaryImportRejectedError("glossary_rejected")
    outcome = GlossaryImportOutcome(
        import_id=UUID(str(row["import_id"])),
        status=GlossaryImportStatus(str(row["status"])),
        entry_count=int(row["entry_count"]),
        alias_count=int(row["alias_count"]),
    )
    LOGGER.info(
        "glossary mutation persisted",
        extra={
            "event": event,
            "import_id": str(outcome.import_id),
            "status": outcome.status.value,
            "entry_count": outcome.entry_count,
            "alias_count": outcome.alias_count,
        },
    )
    return outcome
