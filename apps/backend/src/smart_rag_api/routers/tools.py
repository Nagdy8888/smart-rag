"""Thin permission-filtered tool catalog and owner/admin seed routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import UserRole

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.schemas.fastapi_security import (
    ToolCardResponse,
    ToolEnableRequest,
    ToolMutationResponse,
    ToolPermissionRequest,
    ToolSeedRequest,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.tools_http import ToolHttpService

catalog_router = APIRouter(prefix="/tools", tags=["tools"])
admin_router = APIRouter(prefix="/admin/tools", tags=["tools-admin"])


def get_tool_catalog_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> ToolHttpService:
    """Factory for catalog search with optional seed overlay.

    Args:
        postgres_url: Injected DSN used to overlay ``app.tool_catalog.active``.

    Returns:
        Tool service.
    """

    return ToolHttpService(postgres_url)


def get_tool_admin_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> ToolHttpService:
    """Factory for owner/admin seed writes.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Tool service.
    """

    return ToolHttpService(postgres_url)


@catalog_router.get("", response_model=list[ToolCardResponse])
def search_tools_route(
    request: Request,
    caller: CallerContextDep,
    service: Annotated[ToolHttpService, Depends(get_tool_catalog_service)],
    q: Annotated[str | None, Query(max_length=64)] = None,
) -> list[ToolCardResponse]:
    """Return tools the live role may see. Unauthorized names are omitted.

    Args:
        request: Active request.
        caller: Authenticated caller.
        service: Injected service.
        q: Optional substring filter.

    Returns:
        Permission-filtered cards from the in-code registry.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"tool-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    cards = service.search(caller, query=q)
    return [
        ToolCardResponse(
            tool_key=item.tool_key,
            version_label=item.version_label,
            short_name=item.short_name,
            purpose=item.one_line_purpose,
            required_role=item.required_role.value,
            risk_class=item.risk_class.value,
            active=item.active,
        )
        for item in cards
    ]


@admin_router.post("", response_model=ToolMutationResponse)
def upsert_tool_seed_route(
    request: Request,
    body: ToolSeedRequest,
    caller: CallerContextDep,
    service: Annotated[ToolHttpService, Depends(get_tool_admin_service)],
) -> ToolMutationResponse:
    """Owner/admin catalog seed. Unknown or core keys fail closed.

    Args:
        request: Active request.
        body: Seed payload.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Catalog row id.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"tool-admin:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=20,
    )
    try:
        row_id = service.upsert_seed(
            caller,
            tool_key=body.tool_key,
            display_name=body.display_name,
            description=body.description,
            active=body.active,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return ToolMutationResponse(id=row_id)


@admin_router.post("/{tool_key}/enable", response_model=ToolMutationResponse)
def enable_tool_route(
    request: Request,
    tool_key: str,
    body: ToolEnableRequest,
    caller: CallerContextDep,
    service: Annotated[ToolHttpService, Depends(get_tool_admin_service)],
) -> ToolMutationResponse:
    """Owner/admin enable/disable seed for an allow-listed tool.

    Args:
        request: Active request.
        tool_key: Catalog key.
        body: Active flag.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Catalog row id.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"tool-admin:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=20,
    )
    try:
        row_id = service.enable(caller, tool_key=tool_key, active=body.active)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return ToolMutationResponse(id=row_id)


@admin_router.post("/{tool_key}/permissions", response_model=ToolMutationResponse)
def set_tool_permission_route(
    request: Request,
    tool_key: str,
    body: ToolPermissionRequest,
    caller: CallerContextDep,
    service: Annotated[ToolHttpService, Depends(get_tool_admin_service)],
) -> ToolMutationResponse:
    """Owner/admin permission seed. Executor rechecks live role.

    Args:
        request: Active request.
        tool_key: Catalog key.
        body: Target role and permission.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Permission row id.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"tool-admin:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=20,
    )
    try:
        role = UserRole(body.target_role)
        row_id = service.set_permission(
            caller,
            tool_key=tool_key,
            target_role=role,
            permission=body.permission,
        )
    except ValueError:
        raise_admission_http(QueryAdmissionError("invalid_key"))
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return ToolMutationResponse(id=row_id)
