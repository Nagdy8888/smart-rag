"""HTTP adapter for owner/admin glossary import RPCs."""

from __future__ import annotations

from uuid import UUID

from smart_rag_core.glossary import import_service as glossary_rpc
from smart_rag_core.glossary.import_service import GlossaryImportOutcome
from smart_rag_core.glossary.models import GlossaryBatch

from smart_rag_api.schemas.glossary import ImportGlossaryRequest, request_to_drafts


def import_glossary(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    body: ImportGlossaryRequest,
) -> GlossaryImportOutcome:
    """Persist a pending glossary import for an owner or admin.

    Args:
        postgres_url: Database URL used as ``app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        body: HTTP import body.

    Returns:
        Durable import outcome.

    Raises:
        GlossaryValidationError: If the batch fails closed locally.
        GlossaryImportRejectedError: If the RPC rejects the caller or payload.
    """

    batch = GlossaryBatch(
        source_name=body.source_name,
        source_version=body.source_version,
        idempotency_key=body.idempotency_key,
        entries=request_to_drafts(body),
    )
    return glossary_rpc.import_glossary_batch(
        postgres_url,
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        batch=batch,
    )


def approve_glossary(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    import_id: UUID,
) -> GlossaryImportOutcome:
    """Approve a pending glossary import.

    Args:
        postgres_url: Database URL used as ``app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        import_id: Pending import identifier.

    Returns:
        Updated import outcome.
    """

    return glossary_rpc.approve_glossary_import(
        postgres_url,
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        import_id=import_id,
    )


def rollback_glossary(
    postgres_url: str,
    *,
    caller_user_id: UUID,
    caller_role: str,
    caller_authorization_version: int,
    import_id: UUID,
) -> GlossaryImportOutcome:
    """Roll back an approved glossary import.

    Args:
        postgres_url: Database URL used as ``app_api``.
        caller_user_id: Server-derived subject.
        caller_role: Server-derived role.
        caller_authorization_version: Live authorization snapshot.
        import_id: Import identifier.

    Returns:
        Updated import outcome.
    """

    return glossary_rpc.rollback_glossary_import(
        postgres_url,
        caller_user_id=caller_user_id,
        caller_role=caller_role,
        caller_authorization_version=caller_authorization_version,
        import_id=import_id,
    )
