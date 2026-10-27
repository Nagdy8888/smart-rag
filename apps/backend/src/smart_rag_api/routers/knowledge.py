"""Company knowledge governance endpoints with canonical authorization."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from smart_rag_core.knowledge import DocumentGovernance, UpdateDocumentGovernance
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.knowledge import KnowledgeService

router = APIRouter(prefix="/documents", tags=["knowledge"])


def get_knowledge_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> KnowledgeService:
    """Construct a service without opening database sockets."""
    return KnowledgeService(postgres_url)


@router.get(
    "/{document_id}/governance/versions", response_model=list[DocumentGovernance]
)
def list_governance_versions(
    request: Request,
    document_id: UUID,
    caller: CallerContextDep,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> list[DocumentGovernance]:
    """Read version metadata for owner/admin governance without source-body access."""
    enforce_rate_limit(
        request,
        bucket_key=f"knowledge-versions:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        return service.governance_versions(caller, document_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)


@router.get("/{document_id}/governance", response_model=DocumentGovernance)
def read_governance(
    request: Request,
    document_id: UUID,
    caller: CallerContextDep,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    version_id: UUID | None = None,
) -> DocumentGovernance:
    """Read metadata only when the document remains visible."""
    enforce_rate_limit(
        request,
        bucket_key=f"knowledge-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        return service.governance(caller, document_id, version_id=version_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)


@router.patch("/{document_id}/governance", response_model=DocumentGovernance)
def update_governance(
    request: Request,
    document_id: UUID,
    body: UpdateDocumentGovernance,
    caller: CallerContextDep,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> DocumentGovernance:
    """Owner/admin optimistic update, audited atomically in Postgres."""
    enforce_rate_limit(
        request,
        bucket_key=f"knowledge-write:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    try:
        return service.governance(caller, document_id, body)
    except QueryAdmissionError as exc:
        if exc.reason == "governance_conflict":
            raise HTTPException(409, "governance_conflict") from exc
        if exc.reason == "invalid_governance":
            raise HTTPException(422, "invalid_governance") from exc
        raise_admission_http(exc)
