"""Creator-private document selection; canonical permission checks live in SQL."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from smart_rag_core.knowledge import ConversationKnowledgeScope, UpdateKnowledgeScope
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit
from smart_rag_api.routers.knowledge import get_knowledge_service
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.knowledge import KnowledgeService

router = APIRouter(prefix="/conversations", tags=["knowledge"])


@router.get(
    "/{conversation_id}/knowledge-scope", response_model=ConversationKnowledgeScope
)
def read_scope(
    request: Request,
    conversation_id: UUID,
    caller: CallerContextDep,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> ConversationKnowledgeScope:
    """Show a saved selection without revealing a revoked source title."""
    enforce_rate_limit(
        request,
        bucket_key=f"knowledge-scope:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        return service.scope(caller, conversation_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)


@router.patch(
    "/{conversation_id}/knowledge-scope", response_model=ConversationKnowledgeScope
)
def update_scope(
    request: Request,
    conversation_id: UUID,
    body: UpdateKnowledgeScope,
    caller: CallerContextDep,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> ConversationKnowledgeScope:
    """Set one source for future turns, or explicitly clear it."""
    enforce_rate_limit(
        request,
        bucket_key=f"knowledge-scope-write:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=30,
    )
    try:
        return service.scope(caller, conversation_id, body)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
