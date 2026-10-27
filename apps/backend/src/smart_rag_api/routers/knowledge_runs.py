"""Creator-private durable knowledge outcomes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from smart_rag_core.knowledge import KnowledgeResult
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit
from smart_rag_api.routers.knowledge import get_knowledge_service
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.knowledge import KnowledgeService

router = APIRouter(prefix="/runs", tags=["knowledge"])


@router.get("/{run_id}/knowledge", response_model=KnowledgeResult | None)
def read_run_knowledge(
    request: Request,
    run_id: UUID,
    caller: CallerContextDep,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> KnowledgeResult | None:
    """Read only the caller's outcome; admin role does not grant chat access."""
    enforce_rate_limit(
        request,
        bucket_key=f"knowledge-outcome:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        return service.outcome(caller, run_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
