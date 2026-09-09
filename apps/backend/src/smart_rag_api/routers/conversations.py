"""Thin conversation and Auto message-submit routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse, StreamingResponse
from smart_rag_core.conversations import ConversationRecord
from smart_rag_core.gateways.model import ModelGateway
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import (
    enforce_rate_limit,
    get_model_gateway,
    get_postgres_url,
    get_sse_stream_service,
    get_valkey_limits_client,
)
from smart_rag_api.schemas.fastapi_security import (
    ConversationCreateRequest,
    ConversationMessage,
    ConversationMessagesResponse,
    ConversationResponse,
    SubmitMessageRequest,
    SubmitMessageResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.client_handshake import enforce_client_handshake
from smart_rag_api.services.conversation_transcript import (
    ConversationTranscriptService,
)
from smart_rag_api.services.conversations import ConversationService
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.query_runs import QueryRunService
from smart_rag_api.services.sse_stream import (
    SseStreamService,
    sse_streaming_response,
    wants_event_stream,
)

router = APIRouter(prefix="/conversations", tags=["chat"])


def _conversation_response(
    record: ConversationRecord,
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> ConversationResponse:
    """Map a persisted conversation to JSON.

    Args:
        record: Conversation row.
        prompt_tokens: Provider prompt tokens for this HTTP response. 0 on
            list, get, and create. Title POST returns the billed count or 0
            when the model was skipped.
        completion_tokens: Provider completion tokens for this HTTP response.

    Returns:
        Frozen conversation JSON.
    """

    return ConversationResponse(
        conversation_id=record.conversation_id,
        creator_user_id=record.creator_user_id,
        title=record.title,
        created_at=record.created_at,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


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


def get_conversation_transcript_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> ConversationTranscriptService:
    """Factory for conversation transcript service.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Transcript service.
    """

    return ConversationTranscriptService(postgres_url)


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
    return _conversation_response(record)


@router.get("", response_model=list[ConversationResponse])
def list_conversations_route(
    request: Request,
    caller: CallerContextDep,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=80)] = None,
) -> list[ConversationResponse]:
    """List conversations the caller may read.

    Args:
        request: Active request.
        caller: Authenticated caller.
        service: Injected service.
        limit: Page size, default 50, max 200.
        cursor: Optional ``created_at,id`` keyset cursor.

    Returns:
        Conversation list, newest first.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"chat-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        records = service.list(caller, limit=limit, cursor=cursor)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return [_conversation_response(item) for item in records]


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
    return _conversation_response(record)


@router.post(
    "/{conversation_id}/title",
    response_model=ConversationResponse,
)
async def generate_conversation_title_route(
    request: Request,
    conversation_id: UUID,
    caller: CallerContextDep,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    gateway: Annotated[ModelGateway, Depends(get_model_gateway)],
) -> ConversationResponse:
    """Fill the session title with an LLM summary when it is still a fallback.

    Creator-only. Missing, deleted, and foreign conversations return the same
    generic 404 as ``GET /conversations/{id}``. When the stored title already
    differs from the first-prompt fallback, the existing title is returned
    without a model call. Model failures keep the fallback title.

    Args:
        request: Active request for rate limits.
        conversation_id: Conversation the caller must own.
        caller: Authenticated caller.
        service: Injected conversation service.
        gateway: Process model gateway.

    Returns:
        Conversation JSON. ``prompt_tokens`` and ``completion_tokens`` are
        this title call's provider usage, or 0 when the model was skipped
        or failed.

    Raises:
        HTTPException: 404 for missing, tombstoned, or foreign conversations.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"chat-start:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    try:
        result = await service.generate_title(
            caller,
            conversation_id=conversation_id,
            gateway=gateway,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return _conversation_response(
        result.record,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=ConversationMessagesResponse,
)
def list_conversation_messages_route(
    request: Request,
    conversation_id: UUID,
    caller: CallerContextDep,
    service: Annotated[
        ConversationTranscriptService, Depends(get_conversation_transcript_service)
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[UUID | None, Query()] = None,
) -> ConversationMessagesResponse:
    """List creator-owned user and assistant messages, newest first.

    Authorization is creator-only. Missing, deleted, and foreign
    conversations return the same generic 404 as ``GET /conversations/{id}``.
    Pagination is a keyset on ``before`` (a previous page's last
    ``message_id``). ``limit`` is bounded to 1-100; the SQL RPC also clamps
    to 100. ``next_before_id`` is set only when the page is full.

    Args:
        request: Active request for rate limits.
        conversation_id: Conversation the caller must own.
        caller: Authenticated caller.
        service: Injected transcript service.
        limit: Page size, default 50, maximum 100.
        before: Optional keyset cursor from a prior ``next_before_id``.

    Returns:
        Newest-first page of escaped message records.

    Raises:
        HTTPException: 404 for missing, tombstoned, or foreign conversations.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"chat-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        records = service.list(
            caller,
            conversation_id=conversation_id,
            limit=limit,
            before_id=before,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    items = [
        ConversationMessage(
            message_id=item.message_id,
            role=item.role,
            content=item.content,
            created_at=item.created_at,
        )
        for item in records
    ]
    next_before_id = items[-1].message_id if len(items) == limit else None
    return ConversationMessagesResponse(items=items, next_before_id=next_before_id)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_conversation_route(
    request: Request,
    conversation_id: UUID,
    caller: CallerContextDep,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> Response:
    """Tombstone and purge one owned conversation immediately.

    Args:
        request: Active request for rate limits.
        conversation_id: Conversation id.
        caller: Authenticated caller.
        service: Injected conversation service.

    Returns:
        Empty 204 body.

    Raises:
        HTTPException: 404 for missing, tombstoned, or foreign conversations.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"chat-start:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    try:
        service.delete(caller, conversation_id=conversation_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/messages",
    response_model=None,
    responses={
        202: {"model": SubmitMessageResponse},
        200: {
            "description": "SSE event stream",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        426: {
            "description": "Incompatible client version",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {"type": "string"},
                            "min_client_version": {"type": "string"},
                            "sse_schema_version": {"type": "string"},
                        },
                    }
                }
            },
        },
    },
)
def submit_message_route(
    request: Request,
    conversation_id: UUID,
    body: SubmitMessageRequest,
    caller: CallerContextDep,
    service: Annotated[QueryRunService, Depends(get_query_run_service)],
    sse: Annotated[SseStreamService, Depends(get_sse_stream_service)],
    idempotency_key_header: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
    x_client_version: Annotated[str | None, Header(alias="X-Client-Version")] = None,
) -> JSONResponse | StreamingResponse:
    """Admit Auto chat as Composite. Handshake runs before reservation.

    JSON Accept returns 202 ``{run_id, stream_path}``. ``text/event-stream``
    admits then streams immediately. Duplicate idempotency keys reuse the
    existing run and never reserve twice.

    Args:
        request: Active request.
        conversation_id: Conversation the caller must own.
        body: Message and optional idempotency key.
        caller: Authenticated caller.
        service: Injected query-run service.
        sse: Persist-then-flush SSE service.
        idempotency_key_header: ``Idempotency-Key`` header UUID when the body
            omits the key.
        x_client_version: Required client version for new paid submission.

    Returns:
        JSON admission result or an SSE stream.

    Raises:
        HTTPException: 400 when neither body nor header supplies a key.
    """

    enforce_client_handshake(request, x_client_version)
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="idempotency_key_required",
        )
    try:
        context, stream_path = service.submit_auto_message(
            caller,
            conversation_id=conversation_id,
            idempotency_key=key,
            message=body.message,
            requested_search_scope=body.search_scope,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    sse.remember_admitted(caller, context, message=body.message)
    if wants_event_stream(request.headers.get("accept")):
        return sse_streaming_response(
            sse.iter_frames(
                caller,
                run_id=context.run_id,
                after=0,
                context=context,
            )
        )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=SubmitMessageResponse(
            run_id=context.run_id,
            stream_path=stream_path,
            reconnect=context.reconnect,
            reservation_id=context.reservation_id,
            route_family=context.route_family.value,
            status=context.status,
            requested_search_scope=context.requested_search_scope,
        ).model_dump(mode="json"),
    )
