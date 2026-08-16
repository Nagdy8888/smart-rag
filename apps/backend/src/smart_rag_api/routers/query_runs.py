"""Thin query-run fetch, cancel, citation, and feedback routes. No SSE bodies."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import (
    enforce_rate_limit,
    get_postgres_url,
    get_valkey_limits_client,
)
from smart_rag_api.schemas.fastapi_security import (
    CitationResponse,
    FeedbackRequest,
    FeedbackResponse,
    RunResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.feedback_usage import FeedbackUsageService
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.query_runs import QueryRunService

router = APIRouter(prefix="/runs", tags=["chat"])


def get_query_run_service(
    request: Request,
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> QueryRunService:
    """Factory for run fetch/cancel/citations.

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


def get_feedback_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> FeedbackUsageService:
    """Factory for thumbs feedback.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Feedback/usage service.
    """

    return FeedbackUsageService(postgres_url)


def _run_response(record: QueryRunRecord) -> RunResponse:
    """Map a run record to the HTTP schema.

    Args:
        record: Authorized run record.

    Returns:
        HTTP run payload.
    """

    return RunResponse(
        run_id=record.run_id,
        conversation_id=record.conversation_id,
        creator_user_id=record.creator_user_id,
        status=record.status,
        reservation_id=record.reservation_id,
        created_at=record.created_at,
    )


@router.get("/{run_id}", response_model=RunResponse)
def get_run_route(
    request: Request,
    run_id: UUID,
    caller: CallerContextDep,
    service: Annotated[QueryRunService, Depends(get_query_run_service)],
) -> RunResponse:
    """Fetch one owned run. Foreign runs are 404.

    Args:
        request: Active request.
        run_id: Run id.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Run record.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"run-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        record = service.get(caller, run_id=run_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return _run_response(record)


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run_route(
    request: Request,
    run_id: UUID,
    caller: CallerContextDep,
    service: Annotated[QueryRunService, Depends(get_query_run_service)],
) -> RunResponse:
    """Cancel one owned run. This is not SSE cancel transport.

    Args:
        request: Active request.
        run_id: Run id.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Updated run.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"run-cancel:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    try:
        record = service.cancel(caller, run_id=run_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return _run_response(record)


@router.get("/{run_id}/citations", response_model=list[CitationResponse])
def list_citations_route(
    request: Request,
    run_id: UUID,
    caller: CallerContextDep,
    service: Annotated[QueryRunService, Depends(get_query_run_service)],
) -> list[CitationResponse]:
    """Return citation IDs for an owned run. No passage text.

    Args:
        request: Active request.
        run_id: Run id.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Escaped citation payloads.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"run-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        records = service.citations(caller, run_id=run_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return [
        CitationResponse(
            citation_id=item.citation_id,
            citation_index=item.citation_index,
            chunk_id=item.chunk_id,
            provenance=item.provenance,
        )
        for item in records
    ]


@router.post(
    "/{run_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_feedback_route(
    request: Request,
    run_id: UUID,
    body: FeedbackRequest,
    caller: CallerContextDep,
    service: Annotated[FeedbackUsageService, Depends(get_feedback_service)],
) -> FeedbackResponse:
    """Store thumbs feedback for an owned run.

    Args:
        request: Active request.
        run_id: Run id.
        body: Thumbs flag and optional comment.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Feedback id.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"feedback:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=60,
    )
    try:
        feedback_id = service.submit_thumbs(
            caller,
            run_id=run_id,
            thumbs_up=body.thumbs_up,
            comment=body.comment,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return FeedbackResponse(feedback_id=feedback_id)
