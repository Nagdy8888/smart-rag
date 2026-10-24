"""Thin query-run fetch, cancel, citation, feedback, and SSE resume routes."""

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
from fastapi.responses import StreamingResponse
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.query_admission.service import QueryRunRecord

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import (
    enforce_rate_limit,
    get_postgres_url,
    get_sse_stream_service,
    get_valkey_limits_client,
)
from smart_rag_api.schemas.fastapi_security import (
    CitationDetailResponse,
    CitationResponse,
    FeedbackRequest,
    FeedbackResponse,
    RunResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.citation_page_http import (
    CitationPageReadError,
    CitationPageService,
)
from smart_rag_api.services.feedback_usage import FeedbackUsageService
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.query_runs import QueryRunService
from smart_rag_api.services.sse_stream import (
    SseStreamService,
    resume_after_sequence,
    sse_streaming_response,
)

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


def get_citation_page_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> CitationPageService:
    """Factory for one-page citation PNG reads.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Citation page service.
    """

    return CitationPageService(postgres_url)


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
        requested_search_scope=record.requested_search_scope,
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
    sse: Annotated[SseStreamService, Depends(get_sse_stream_service)],
) -> RunResponse:
    """Cancel one owned run, stop the live SSE generator, and persist cancelled.

    Args:
        request: Active request.
        run_id: Run id.
        caller: Authenticated caller.
        service: Injected query-run service.
        sse: SSE service used to stop the live generator.

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
        sse.notify_cancel(caller, run_id=run_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return _run_response(record)


@router.get(
    "/{run_id}/events",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE event stream",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
def stream_run_events_route(
    request: Request,
    run_id: UUID,
    caller: CallerContextDep,
    sse: Annotated[SseStreamService, Depends(get_sse_stream_service)],
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Replay persisted events after ``after`` / ``Last-Event-ID``. Bearer only.

    Handshake is not required. Foreign, missing, or tombstoned runs are 404.
    Reconnect never starts a second paid graph.

    Args:
        request: Active request.
        run_id: Run id.
        caller: Authenticated owner.
        sse: Persist-then-flush service.
        after: Exclusive sequence cursor. ``0`` means from the start.
        last_event_id: SSE reconnect header honored when higher than ``after``.

    Returns:
        ``text/event-stream`` body.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"run-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    cursor = resume_after_sequence(after, last_event_id)
    try:
        sse.assert_readable(caller, run_id=run_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return sse_streaming_response(sse.iter_frames(caller, run_id=run_id, after=cursor))


@router.get("/{run_id}/citations", response_model=list[CitationResponse])
def list_citations_route(
    request: Request,
    run_id: UUID,
    caller: CallerContextDep,
    service: Annotated[QueryRunService, Depends(get_query_run_service)],
) -> list[CitationResponse]:
    """Return citation IDs and ACL-checked excerpts for an owned run.

    Args:
        request: Active request.
        run_id: Run id.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Escaped citation payloads. Excerpt is never placed in provenance.
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
            source_unavailable=item.source_unavailable,
            source_kind=item.source_kind,
            web_source_id=item.web_source_id,
            paragraph_index=item.paragraph_index,
            document_title=item.document_title,
            pdf_page_number=item.pdf_page_number,
            evidence_excerpt=item.evidence_excerpt,
        )
        for item in records
    ]


@router.get(
    "/{run_id}/citations/{citation_id}",
    response_model=CitationDetailResponse,
)
def get_citation_detail_route(
    request: Request,
    run_id: UUID,
    citation_id: UUID,
    caller: CallerContextDep,
    service: Annotated[QueryRunService, Depends(get_query_run_service)],
) -> CitationDetailResponse:
    """Return one owned citation with a bounded ACL-checked excerpt.

    Args:
        request: Active request.
        run_id: Run id.
        citation_id: Citation id on that run.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Escaped detail payload. Web URLs are HTTPS only. Unavailable
        sources omit the excerpt.

    Raises:
        HTTPException: 404 for missing, foreign, or mismatched IDs.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"run-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        detail = service.citation_detail(caller, run_id=run_id, citation_id=citation_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    item = detail.citation
    return CitationDetailResponse(
        citation_id=item.citation_id,
        citation_index=item.citation_index,
        chunk_id=item.chunk_id,
        provenance=item.provenance,
        source_unavailable=item.source_unavailable,
        source_kind=item.source_kind,
        web_source_id=item.web_source_id,
        paragraph_index=item.paragraph_index,
        document_title=item.document_title,
        pdf_page_number=item.pdf_page_number,
        evidence_excerpt=item.evidence_excerpt,
        source_url=detail.source_url,
    )


@router.get("/{run_id}/citations/{citation_id}/page")
def get_citation_page_route(
    request: Request,
    run_id: UUID,
    citation_id: UUID,
    caller: CallerContextDep,
    service: Annotated[CitationPageService, Depends(get_citation_page_service)],
) -> Response:
    """Return a PNG of one authorized PDF page. No Storage URL.

    Args:
        request: Active request.
        run_id: Run id.
        citation_id: Citation id on that run.
        caller: Authenticated caller.
        service: Injected page renderer.

    Returns:
        PNG bytes for that file page only.

    Raises:
        HTTPException: 404 when the citation is foreign, unavailable, or
            the page cannot be rendered.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"run-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    try:
        png = service.read_png(caller, run_id=run_id, citation_id=citation_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except CitationPageReadError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store"},
    )


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
        body: Thumbs flag, required tag, and optional comment.
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
            tag=body.tag,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return FeedbackResponse(feedback_id=feedback_id)
