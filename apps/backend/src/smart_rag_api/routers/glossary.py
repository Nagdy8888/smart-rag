"""Owner/admin glossary import routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from smart_rag_core.glossary.import_service import GlossaryImportRejectedError
from smart_rag_core.glossary.validation import GlossaryValidationError
from smart_rag_core.security.identity import UserRole
from smart_rag_core.settings import BackendSettings

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit
from smart_rag_api.schemas.glossary import GlossaryImportResponse, ImportGlossaryRequest
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.glossary_import import (
    approve_glossary,
    import_glossary,
    rollback_glossary,
)

router = APIRouter(prefix="/admin/glossary", tags=["glossary"])


def _postgres_url(request: Request) -> str:
    """Return the backend Postgres URL or fail closed.

    Args:
        request: FastAPI request with startup settings.

    Returns:
        Database URL string.

    Raises:
        HTTPException: 503 when the database URL is unset.
    """

    settings: BackendSettings = request.app.state.settings
    if settings.supabase_db_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unconfigured",
        )
    return settings.supabase_db_url.get_secret_value()


def _require_owner_admin(caller: CallerContextDep) -> None:
    """Reject members and viewers.

    Args:
        caller: Authenticated caller context.

    Raises:
        HTTPException: 403 when the caller is not owner or admin.
    """

    if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _rate_admin_mutation(request: Request, caller: CallerContextDep) -> None:
    """Apply FastAPI-owned admin mutation limits.

    Args:
        request: Active request.
        caller: Authenticated owner/admin.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"glossary-admin:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=20,
    )


@router.post(
    "/imports",
    response_model=GlossaryImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_glossary_import(
    request: Request,
    body: ImportGlossaryRequest,
    caller: CallerContextDep,
) -> GlossaryImportResponse:
    """Import a pending glossary batch. Members cannot seed aliases.

    Args:
        request: FastAPI request with backend settings.
        body: Source, version, idempotency key, and entries.
        caller: Authenticated caller context.

    Returns:
        Import identifiers. Duplicate idempotency keys reuse one row.

    Raises:
        HTTPException: 403 for members/viewers, 400 for validation failures,
            503 when the database URL is unset.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        outcome = import_glossary(
            _postgres_url(request),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
            body=body,
        )
    except (GlossaryValidationError, GlossaryImportRejectedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.reason,
        ) from exc
    return GlossaryImportResponse(
        import_id=outcome.import_id,
        status=outcome.status.value,
        entry_count=outcome.entry_count,
        alias_count=outcome.alias_count,
    )


@router.post(
    "/imports/{import_id}/approve",
    response_model=GlossaryImportResponse,
)
def approve_glossary_import_route(
    request: Request,
    import_id: UUID,
    caller: CallerContextDep,
) -> GlossaryImportResponse:
    """Approve a pending import and project aliases into search_aliases.

    Args:
        request: FastAPI request with backend settings.
        import_id: Pending import identifier.
        caller: Authenticated caller context.

    Returns:
        Updated import identifiers.

    Raises:
        HTTPException: 403 for members/viewers, 400 when approval is rejected.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        outcome = approve_glossary(
            _postgres_url(request),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
            import_id=import_id,
        )
    except GlossaryImportRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.reason,
        ) from exc
    return GlossaryImportResponse(
        import_id=outcome.import_id,
        status=outcome.status.value,
        entry_count=outcome.entry_count,
        alias_count=outcome.alias_count,
    )


@router.post(
    "/imports/{import_id}/rollback",
    response_model=GlossaryImportResponse,
)
def rollback_glossary_import_route(
    request: Request,
    import_id: UUID,
    caller: CallerContextDep,
) -> GlossaryImportResponse:
    """Roll back an approved import by deleting its search projection.

    Args:
        request: FastAPI request with backend settings.
        import_id: Import identifier.
        caller: Authenticated caller context.

    Returns:
        Updated import identifiers.

    Raises:
        HTTPException: 403 for members/viewers, 400 when rollback is rejected.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        outcome = rollback_glossary(
            _postgres_url(request),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
            import_id=import_id,
        )
    except GlossaryImportRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.reason,
        ) from exc
    return GlossaryImportResponse(
        import_id=outcome.import_id,
        status=outcome.status.value,
        entry_count=outcome.entry_count,
        alias_count=outcome.alias_count,
    )
