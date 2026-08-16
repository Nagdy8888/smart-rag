"""Thin conversation and Auto message-submit routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import (
    enforce_rate_limit,
    get_postgres_url,
    get_valkey_limits_client,
)
from smart_rag_api.schemas.fastapi_security import (
    ConversationCreateRequest,
    ConversationResponse,
    SubmitMessageRequest,
    SubmitMessageResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.conversations import (
    ConversationService,
    conversation_delete_not_implemented,
)
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.query_runs import QueryRunService

router = APIRouter(prefix="/conversations", tags=["chat"])


def get_conversation_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> ConversationService:
    """Factory for conversation service.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Conversation service.
    """

    return ConversationService(postgres_url)


def get_query_run_service(
    request: Request,
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> QueryRunService:
    """Factory for query-run service.

    Args:
        request: Active request.
        postgres_url: Injected DSN.

    Returns:
        Query-run service.
    """

    return QueryRunService(
        postgres_url,
        valkey_client=get_valkey_limits_client(request),
    )


@router.post(
    "", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED
)
def create_conversation_route(
    request: Request,
    body: ConversationCreateRequest,
    caller: CallerContextDep,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationResponse:
    """Create a creator-owned conversation.

    Args:
        request: Active request for rate limits.
        body: Optional title.
        caller: Authenticated caller.
        service: Injected conversation service.

    Returns:
        Created conversation.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"chat-start:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    try:
        record = service.create(caller, title=body.title)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return ConversationResponse(
        conversation_id=record.conversation_id,
        creator_user_id=record.creator_user_id,
        title=record.title,
        created_at=record.created_at,
    )


@router.get("", response_model=list[ConversationResponse])
def list_conversations_route(
    request: Request,
    caller: CallerContextDep,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> list[ConversationResponse]:
    """List conversations the caller may read.

    Args:
        request: Active request.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Conversation list.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"chat-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    records = service.list(caller)
    return [
        ConversationResponse(
            conversation_id=item.conversation_id,
            creator_user_id=item.creator_user_id,
            title=item.title,
            created_at=item.created_at,
        )
        for item in records
    ]


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation_route(
    request: Request,
    conversation_id: UUID,
    caller: CallerContextDep,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationResponse:
    """Get one non-deleted conversation.

    Args:
        request: Active request.
        conversation_id: Conversation id.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Conversation record.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"chat-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        record = service.get(caller, conversation_id=conversation_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return ConversationResponse(
        conversation_id=record.conversation_id,
        creator_user_id=record.creator_user_id,
        title=record.title,
        created_at=record.created_at,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def delete_conversation_route(
    conversation_id: UUID,
    caller: CallerContextDep,
) -> dict[str, str]:
    """Conversation deletion is packet 7. This packet fails closed.

    Args:
        conversation_id: Conversation id (authorization still required).
        caller: Authenticated caller.

    Returns:
        Never a success body.

    Raises:
        HTTPException: 501 ``conversation_deletion_not_implemented``.
    """

    del conversation_id, caller
    try:
        conversation_delete_not_implemented()
    except QueryAdmissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=exc.reason,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="conversation_deletion_not_implemented",
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=SubmitMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_message_route(
    request: Request,
    conversation_id: UUID,
    body: SubmitMessageRequest,
    caller: CallerContextDep,
    service: Annotated[QueryRunService, Depends(get_query_run_service)],
    idempotency_key_header: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
) -> SubmitMessageResponse:
    """Admit Auto chat as Composite. Returns stream_path without SSE bodies.

    Args:
        request: Active request.
        conversation_id: Conversation the caller must own.
        body: Message and optional idempotency key.
        caller: Authenticated caller.
        service: Injected query-run service.
        idempotency_key_header: Optional ``Idempotency-Key`` header UUID.

    Returns:
        ``run_id``, ``stream_path``, reconnect flag.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"chat-start:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    key = body.idempotency_key
    if key is None and idempotency_key_header:
        try:
            key = UUID(idempotency_key_header)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="validation_failed",
            ) from exc
    if key is None:
        key = uuid4()
    try:
        context, stream_path = service.submit_auto_message(
            caller,
            conversation_id=conversation_id,
            idempotency_key=key,
            message=body.message,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return SubmitMessageResponse(
        run_id=context.run_id,
        stream_path=stream_path,
        reconnect=context.reconnect,
        reservation_id=context.reservation_id,
        route_family=context.route_family.value,
        status=context.status,
    )
