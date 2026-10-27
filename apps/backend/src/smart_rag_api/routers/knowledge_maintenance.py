"""Owner/admin knowledge review; source access and report consent stay in SQL."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from smart_rag_core.knowledge import MaintenanceItem, MaintenanceKind, MaintenanceUpdate
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.knowledge_maintenance import MaintenanceService

router = APIRouter(prefix="/admin/knowledge", tags=["knowledge"])


def get_maintenance_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> MaintenanceService:
    """Construct the request's maintenance service."""
    return MaintenanceService(postgres_url)


@router.get("/maintenance", response_model=list[MaintenanceItem])
def list_maintenance(
    request: Request,
    caller: CallerContextDep,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> list[MaintenanceItem]:
    """List currently visible tasks without granting access to private threads."""
    enforce_rate_limit(
        request,
        bucket_key=f"knowledge-queue:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        return service.list(caller, limit=limit, offset=offset)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)


@router.patch("/maintenance/{kind}/{source_id}", status_code=204)
def update_maintenance(
    request: Request,
    kind: MaintenanceKind,
    source_id: UUID,
    body: MaintenanceUpdate,
    caller: CallerContextDep,
    service: Annotated[MaintenanceService, Depends(get_maintenance_service)],
) -> Response:
    """Record an assignment or reasoned resolution with revision checking."""
    enforce_rate_limit(
        request,
        bucket_key=f"knowledge-review:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=30,
    )
    try:
        service.update(caller, kind, source_id, body)
    except QueryAdmissionError as exc:
        if exc.reason == "governance_conflict":
            raise HTTPException(409, "governance_conflict") from exc
        if exc.reason == "invalid_review":
            raise HTTPException(422, "invalid_review") from exc
        raise_admission_http(exc)
    return Response(status_code=204)
