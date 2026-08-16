"""Owner/admin graph entity-rule routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from smart_rag_core.jobs.entity_rules import EntityRuleRejectedError
from smart_rag_core.jobs.exceptions import GraphEntityRuleError
from smart_rag_core.security.identity import UserRole
from smart_rag_core.settings import BackendSettings

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit
from smart_rag_api.schemas.entity_rules import (
    EntityRuleConcurrencyRequest,
    EntityRuleListResponse,
    EntityRuleMutationResponse,
    EntityRuleSuggestRequest,
    EntityRuleUpsertRequest,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.entity_rules import (
    approve_entity_rule_http,
    create_entity_rule_suggestion,
    create_or_update_entity_rule,
    list_entity_rules_http,
    revoke_entity_rule_http,
)

router = APIRouter(prefix="/admin/graph/entity-rules", tags=["graph-entity-rules"])

_CONFLICT_REASONS = {"stale_row_version", "already_approved", "already_revoked"}
_FORBIDDEN_REASONS = {"forbidden"}


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
        bucket_key=f"entity-rules-admin:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=20,
    )


def _raise_rule_error(exc: EntityRuleRejectedError | GraphEntityRuleError) -> None:
    """Map rule failures to sanitized HTTP errors.

    Args:
        exc: Validation or RPC rejection.

    Raises:
        HTTPException: 403, 409, or 400 with a reason code only.
    """

    reason = exc.reason
    if reason in _FORBIDDEN_REASONS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=reason
        ) from exc
    if reason in _CONFLICT_REASONS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=reason
        ) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason) from exc


@router.get("", response_model=EntityRuleListResponse)
def list_entity_rules_route(
    request: Request,
    caller: CallerContextDep,
) -> EntityRuleListResponse:
    """List curated and suggested entity rules. Members receive 403.

    Args:
        request: FastAPI request with backend settings.
        caller: Authenticated caller context.

    Returns:
        Rule listing. Native LightRAG names are not copied into Hybrid aliases.

    Raises:
        HTTPException: 403 for members/viewers, 503 when unconfigured.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        return list_entity_rules_http(
            _postgres_url(request),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
        )
    except GraphEntityRuleError as exc:
        _raise_rule_error(exc)
        raise


@router.post(
    "",
    response_model=EntityRuleMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_entity_rule_route(
    request: Request,
    body: EntityRuleUpsertRequest,
    caller: CallerContextDep,
) -> EntityRuleMutationResponse:
    """Create an approved admin rule or a typed draft. Members receive 403.

    Args:
        request: FastAPI request with backend settings.
        body: Rule payload. Feedback/model sources cannot be auto-approved.
        caller: Authenticated caller context.

    Returns:
        Mutation identifiers. Approved writes schedule rebuild isolation.

    Raises:
        HTTPException: 403 for members/viewers, 400 for validation.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        return create_or_update_entity_rule(
            _postgres_url(request),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
            body=body,
        )
    except (EntityRuleRejectedError, GraphEntityRuleError) as exc:
        _raise_rule_error(exc)
        raise


@router.patch("/{rule_id}", response_model=EntityRuleMutationResponse)
def update_entity_rule_route(
    request: Request,
    rule_id: UUID,
    body: EntityRuleUpsertRequest,
    caller: CallerContextDep,
) -> EntityRuleMutationResponse:
    """Update one rule with optimistic concurrency. Members receive 403.

    Args:
        request: FastAPI request with backend settings.
        rule_id: Existing rule identifier.
        body: Updated payload including ``row_version``.
        caller: Authenticated caller context.

    Returns:
        Mutation identifiers.

    Raises:
        HTTPException: 403, 409 for stale versions, 400 for validation.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        return create_or_update_entity_rule(
            _postgres_url(request),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
            body=body,
            rule_id=rule_id,
        )
    except (EntityRuleRejectedError, GraphEntityRuleError) as exc:
        _raise_rule_error(exc)
        raise


@router.post(
    "/suggestions",
    response_model=EntityRuleMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def suggest_entity_rule_route(
    request: Request,
    body: EntityRuleSuggestRequest,
    caller: CallerContextDep,
) -> EntityRuleMutationResponse:
    """Store an inactive feedback/model suggestion. Never auto-approves.

    Args:
        request: FastAPI request with backend settings.
        body: Suggestion payload with provenance/confidence.
        caller: Authenticated caller context.

    Returns:
        Identifiers with ``invalidated=false``.

    Raises:
        HTTPException: 403 for members/viewers, 400 for validation.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        return create_entity_rule_suggestion(
            _postgres_url(request),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
            body=body,
        )
    except (EntityRuleRejectedError, GraphEntityRuleError) as exc:
        _raise_rule_error(exc)
        raise


@router.post("/{rule_id}/approve", response_model=EntityRuleMutationResponse)
def approve_entity_rule_route(
    request: Request,
    rule_id: UUID,
    body: EntityRuleConcurrencyRequest,
    caller: CallerContextDep,
) -> EntityRuleMutationResponse:
    """Explicitly approve a suggestion and schedule a clean rebuild.

    Args:
        request: FastAPI request with backend settings.
        rule_id: Suggestion identifier.
        body: Expected ``row_version``.
        caller: Authenticated caller context.

    Returns:
        Mutation identifiers with invalidation/rebuild job ids.

    Raises:
        HTTPException: 403, 409, or 400.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        return approve_entity_rule_http(
            _postgres_url(request),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
            rule_id=rule_id,
            row_version=body.row_version,
        )
    except GraphEntityRuleError as exc:
        _raise_rule_error(exc)
        raise


@router.post("/{rule_id}/revoke", response_model=EntityRuleMutationResponse)
def revoke_entity_rule_route(
    request: Request,
    rule_id: UUID,
    body: EntityRuleConcurrencyRequest,
    caller: CallerContextDep,
) -> EntityRuleMutationResponse:
    """Revoke a rule. Approved revocations invalidate maps.

    Args:
        request: FastAPI request with backend settings.
        rule_id: Rule identifier.
        body: Expected ``row_version``.
        caller: Authenticated caller context.

    Returns:
        Mutation identifiers.

    Raises:
        HTTPException: 403, 409, or 400.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        return revoke_entity_rule_http(
            _postgres_url(request),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
            rule_id=rule_id,
            row_version=body.row_version,
        )
    except GraphEntityRuleError as exc:
        _raise_rule_error(exc)
        raise
