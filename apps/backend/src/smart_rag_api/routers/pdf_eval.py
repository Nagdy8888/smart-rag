"""Local/test owner/admin hosted quiz-case and exam routes."""

from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from smart_rag_core.evaluation.private_pdf.exam_fingerprint import (
    capture_exam_candidate_fingerprint,
)
from smart_rag_core.evaluation.private_pdf.exam_repository import (
    ExamMigrationMissingError,
    ExamRepository,
    ExamRepositoryError,
)
from smart_rag_core.evaluation.private_pdf.quiz_repository import (
    QuizCaseDetail,
    QuizCaseSummary,
    QuizMigrationMissingError,
    QuizRepositoryError,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import UserRole
from smart_rag_core.settings import BackendSettings, Environment

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.routers.query_runs import get_query_run_service
from smart_rag_api.schemas.pdf_eval import (
    PdfEvalCaseCreateRequest,
    PdfEvalCaseDetailResponse,
    PdfEvalCaseListResponse,
    PdfEvalCasePatchRequest,
    PdfEvalCaseSummaryResponse,
    PdfEvalCompareRunRequest,
    PdfEvalCompareRunResponse,
    PdfEvalExamAcceptedResponse,
    PdfEvalExamCaseListResponse,
    PdfEvalExamCaseResponse,
    PdfEvalExamReportResponse,
    PdfEvalExamStartRequest,
    PdfEvalExamStatusResponse,
    PdfEvalGoldLocatorResponse,
    PdfEvalGoldReplaceRequest,
    PdfEvalMutationResponse,
    PdfEvalPassageListResponse,
    PdfEvalPassageResponse,
    PdfEvalRegenerateRequest,
    PdfEvalRevisionRequest,
    PdfEvalStatusResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.eval_exam_supervisor import bind_exam_http_runtime
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.pdf_eval_workspace import (
    PdfEvalWorkspaceService,
    build_quiz_repository,
)
from smart_rag_api.services.query_runs import QueryRunService

router = APIRouter(prefix="/admin/pdf-eval", tags=["pdf-eval"])

_QUIZ_HTTP: dict[str, int] = {
    "quiz_schema_missing": status.HTTP_503_SERVICE_UNAVAILABLE,
    "not_found": status.HTTP_404_NOT_FOUND,
    "forbidden": status.HTTP_403_FORBIDDEN,
    "authorization_rejected": status.HTTP_403_FORBIDDEN,
    "stale_row_version": status.HTTP_409_CONFLICT,
    "idempotency_collision": status.HTTP_409_CONFLICT,
    "capacity_exceeded": status.HTTP_409_CONFLICT,
    "holdout_rejected": status.HTTP_400_BAD_REQUEST,
    "class_invalid": status.HTTP_400_BAD_REQUEST,
    "question_invalid": status.HTTP_400_BAD_REQUEST,
    "gold_limit": status.HTTP_400_BAD_REQUEST,
    "gold_duplicate": status.HTTP_400_BAD_REQUEST,
    "gold_version_mismatch": status.HTTP_400_BAD_REQUEST,
    "gold_required": status.HTTP_400_BAD_REQUEST,
    "gold_stale": status.HTTP_400_BAD_REQUEST,
    "answer_required": status.HTTP_400_BAD_REQUEST,
    "family_required": status.HTTP_400_BAD_REQUEST,
    "family_split_conflict": status.HTTP_400_BAD_REQUEST,
}

_EXAM_HTTP: dict[str, int] = {
    "exam_schema_missing": status.HTTP_503_SERVICE_UNAVAILABLE,
    "incomplete_fingerprint": status.HTTP_503_SERVICE_UNAVAILABLE,
    "hybrid_unbound": status.HTTP_503_SERVICE_UNAVAILABLE,
    "not_found": status.HTTP_404_NOT_FOUND,
    "forbidden": status.HTTP_403_FORBIDDEN,
    "authorization_rejected": status.HTTP_403_FORBIDDEN,
    "holdout_rejected": status.HTTP_400_BAD_REQUEST,
    "split_invalid": status.HTTP_400_BAD_REQUEST,
    "idempotency_invalid": status.HTTP_400_BAD_REQUEST,
    "fingerprint_invalid": status.HTTP_400_BAD_REQUEST,
    "already_running": status.HTTP_409_CONFLICT,
    "idempotency_collision": status.HTTP_409_CONFLICT,
    "qualification_consumed": status.HTTP_409_CONFLICT,
    "stale_dataset_hash": status.HTTP_409_CONFLICT,
    "empty_dataset": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "gold_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "gold_stale": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def pdf_eval_routes_enabled(settings: BackendSettings) -> bool:
    """Return whether PDF eval routes may be registered.

    Args:
        settings: Backend settings.

    Returns:
        True only when the flag is on and ``APP_ENV`` is local or test.
    """

    return bool(settings.pdf_eval_workspace_enabled) and settings.app_env in {
        Environment.LOCAL,
        Environment.TEST,
    }


def get_pdf_eval_service(
    request: Request,
    postgres_url: Annotated[str, Depends(get_postgres_url)],
    query_runs: Annotated[QueryRunService, Depends(get_query_run_service)],
) -> PdfEvalWorkspaceService:
    """Build the workspace service from server-owned settings.

    Args:
        request: Request with backend settings.
        postgres_url: ``app_api`` DSN.
        query_runs: Owned-run service.

    Returns:
        Workspace service.

    Raises:
        HTTPException: 404 when the workspace is disabled.
    """

    settings: BackendSettings = request.app.state.settings
    if not pdf_eval_routes_enabled(settings):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return PdfEvalWorkspaceService(
        repository=build_quiz_repository(postgres_url),
        postgres_url=postgres_url,
        query_runs=query_runs,
    )


def get_exam_repository(
    request: Request,
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> ExamRepository:
    """Build the exam RPC wrapper from server-owned settings.

    Args:
        request: Request with backend settings.
        postgres_url: ``app_api`` DSN.

    Returns:
        Exam repository.

    Raises:
        HTTPException: 404 when the workspace is disabled.
    """

    settings: BackendSettings = request.app.state.settings
    if not pdf_eval_routes_enabled(settings):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return ExamRepository(postgres_url)


def _require_owner_admin(caller: CallerContextDep) -> None:
    """Reject members and viewers.

    Args:
        caller: Authenticated caller.

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
        bucket_key=f"pdf-eval-admin:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=20,
    )


def _rate_exam_mutation(request: Request, caller: CallerContextDep) -> None:
    """Apply FastAPI-owned cost mutation limits for exam start/cancel.

    Args:
        request: Active request.
        caller: Authenticated owner/admin.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"pdf-eval-exam:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )


def _rate_exam_read(request: Request, caller: CallerContextDep) -> None:
    """Apply FastAPI-owned safe-read limits for exam poll/report.

    Args:
        request: Active request.
        caller: Authenticated owner/admin.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"pdf-eval-exam-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )


def _raise_quiz(exc: Exception) -> NoReturn:
    """Raise the matching HTTP error for a quiz failure.

    Args:
        exc: Repository or validation exception.

    Raises:
        HTTPException: Mapped status. Missing schema is 503, not empty.
    """

    if isinstance(exc, QuizMigrationMissingError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="quiz_schema_missing",
        ) from exc
    if isinstance(exc, QuizRepositoryError):
        raise HTTPException(
            status_code=_QUIZ_HTTP.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=exc.code,
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="request_rejected",
    ) from exc


def _raise_exam(exc: Exception) -> NoReturn:
    """Raise the matching HTTP error for an exam failure.

    Args:
        exc: Repository exception.

    Raises:
        HTTPException: Mapped status. Missing schema is 503.
    """

    if isinstance(exc, ExamMigrationMissingError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="exam_schema_missing",
        ) from exc
    if isinstance(exc, ExamRepositoryError):
        raise HTTPException(
            status_code=_EXAM_HTTP.get(exc.code, status.HTTP_400_BAD_REQUEST),
            detail=exc.code,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="request_rejected",
    ) from exc


def _summary(case: QuizCaseSummary) -> PdfEvalCaseSummaryResponse:
    """Build a list row without private question fields.

    Args:
        case: Summary record.

    Returns:
        Summary response.
    """

    return PdfEvalCaseSummaryResponse(
        case_id=case.case_id,
        split=case.split,
        query_class=case.query_class,
        review_status=case.review_status,
        generated_only=case.generated_only,
        source_family_id=case.source_family_id,
        gold_chunk_count=case.gold_chunk_count,
        gold_stale=case.gold_stale,
        row_version=case.row_version,
        human_approved=case.review_status == "approved",
    )


def _detail(case: QuizCaseDetail) -> PdfEvalCaseDetailResponse:
    """Build a case detail body.

    Args:
        case: Detail record.

    Returns:
        Detail response.
    """

    return PdfEvalCaseDetailResponse(
        case_id=case.case_id,
        split=case.split,
        query_class=case.query_class,
        review_status=case.review_status,
        generated_only=case.generated_only,
        source_family_id=case.source_family_id,
        question=case.question,
        expected_answer=case.expected_answer,
        atomic_facts=case.atomic_facts,
        required_terms=case.required_terms,
        expected_scope=case.expected_scope,
        source_run_id=case.source_run_id,
        document_id=case.document_id,
        version_id=case.version_id,
        gold=tuple(
            PdfEvalGoldLocatorResponse(
                ordinal=item.ordinal,
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                version_id=item.version_id,
                page_number=item.page_number,
                page_label=item.page_label,
                section_path=item.section_path,
                stale=item.stale,
            )
            for item in case.gold
        ),
        gold_stale=case.gold_stale,
        reviewer_user_id=case.reviewer_user_id,
        row_version=case.row_version,
        human_approved=case.review_status == "approved",
    )


@router.get("/status", response_model=PdfEvalStatusResponse)
def pdf_eval_status(
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalStatusResponse:
    """Return workspace status. Disabled mode is 404. Missing schema is 503.

    Args:
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        Status without questions or filesystem paths.
    """

    _require_owner_admin(caller)
    try:
        payload = service.status(caller)
    except Exception as exc:
        _raise_quiz(exc)
    return PdfEvalStatusResponse.model_validate(payload)


@router.post("/cases", response_model=PdfEvalMutationResponse, status_code=201)
def create_pdf_eval_case(
    body: PdfEvalCaseCreateRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Create a draft from a caller-owned completed run.

    Args:
        body: Run id, labels, optional gold IDs, idempotency key.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        Case id and row version.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        result = service.create_case(
            caller,
            source_run_id=body.source_run_id,
            expected_answer=body.expected_answer,
            atomic_facts=body.atomic_facts,
            query_class=body.query_class,
            required_terms=body.required_terms,
            split=body.split,
            source_family_id=body.source_family_id,
            chunk_ids=body.chunk_ids,
            idempotency_key=body.idempotency_key,
        )
    except Exception as exc:
        _raise_quiz(exc)
    return PdfEvalMutationResponse(
        case_id=result.case_id,
        row_version=result.row_version,
        replayed=result.replayed,
    )


@router.get("/cases", response_model=PdfEvalCaseListResponse)
def list_pdf_eval_cases(
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
    split: Annotated[str | None, Query(max_length=32)] = None,
    review_status: Annotated[str | None, Query(max_length=32)] = None,
    after: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
) -> PdfEvalCaseListResponse:
    """List case summaries without bulk question fields.

    Args:
        caller: Authenticated caller.
        service: Workspace service.
        split: Optional split filter. ``holdout`` is rejected.
        review_status: Optional ``draft``, ``approved``, or ``rejected``.
        after: Keyset cursor.
        limit: Page size.

    Returns:
        Summaries.
    """

    _require_owner_admin(caller)
    if review_status is not None and review_status not in {
        "draft",
        "approved",
        "rejected",
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="validation_failed",
        )
    try:
        items = service.list_cases(
            caller,
            split=split,
            review_status=review_status,
            after_case_id=after,
            limit=limit,
        )
    except Exception as exc:
        _raise_quiz(exc)
    next_id = items[-1].case_id if len(items) == limit else None
    return PdfEvalCaseListResponse(
        items=[_summary(case) for case in items],
        next_case_id=next_id,
    )


@router.get("/cases/{case_id}", response_model=PdfEvalCaseDetailResponse)
def get_pdf_eval_case(
    case_id: UUID,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalCaseDetailResponse:
    """Return one case including private question fields.

    Args:
        case_id: Case identifier.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        Case detail.
    """

    _require_owner_admin(caller)
    try:
        case = service.get_case(caller, case_id)
    except Exception as exc:
        _raise_quiz(exc)
    return _detail(case)


@router.patch("/cases/{case_id}", response_model=PdfEvalMutationResponse)
def patch_pdf_eval_case(
    case_id: UUID,
    body: PdfEvalCasePatchRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Edit editable fields. Cannot set reviewer, approval, or split.

    Args:
        case_id: Case identifier.
        body: Patch plus expected row version.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        New row version.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        mutated_id, row_version = service.patch_case(
            caller,
            case_id,
            expected_row_version=body.expected_row_version,
            question=body.question,
            expected_answer=body.expected_answer,
            atomic_facts=body.atomic_facts,
            query_class=body.query_class,
            required_terms=body.required_terms,
            source_family_id=body.source_family_id,
            expected_scope=body.expected_scope,
        )
    except Exception as exc:
        _raise_quiz(exc)
    return PdfEvalMutationResponse(case_id=mutated_id, row_version=row_version)


@router.put("/cases/{case_id}/gold", response_model=PdfEvalMutationResponse)
def replace_pdf_eval_gold(
    case_id: UUID,
    body: PdfEvalGoldReplaceRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Replace gold locators from current authorized chunk IDs.

    Args:
        case_id: Case identifier.
        body: Chunk IDs plus expected row version.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        New row version.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        mutated_id, row_version, gold_count = service.replace_gold(
            caller,
            case_id,
            expected_row_version=body.expected_row_version,
            chunk_ids=body.chunk_ids,
        )
    except Exception as exc:
        _raise_quiz(exc)
    return PdfEvalMutationResponse(
        case_id=mutated_id,
        row_version=row_version,
        gold_chunk_count=gold_count,
    )


@router.post("/cases/{case_id}/approve", response_model=PdfEvalMutationResponse)
def approve_pdf_eval_case(
    case_id: UUID,
    body: PdfEvalRevisionRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Approve a case. Reviewer is ``caller.user_id``.

    Args:
        case_id: Case identifier.
        body: Expected row version.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        New row version.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        mutated_id, row_version = service.approve(
            caller, case_id, expected_row_version=body.expected_row_version
        )
    except Exception as exc:
        _raise_quiz(exc)
    return PdfEvalMutationResponse(case_id=mutated_id, row_version=row_version)


@router.post("/cases/{case_id}/reject", response_model=PdfEvalMutationResponse)
def reject_pdf_eval_case(
    case_id: UUID,
    body: PdfEvalRevisionRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Reject a case after named-human inspection.

    Args:
        case_id: Case identifier.
        body: Expected row version.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        New row version.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        mutated_id, row_version = service.reject(
            caller, case_id, expected_row_version=body.expected_row_version
        )
    except Exception as exc:
        _raise_quiz(exc)
    return PdfEvalMutationResponse(case_id=mutated_id, row_version=row_version)


@router.delete("/cases/{case_id}", response_model=PdfEvalMutationResponse)
def delete_pdf_eval_case(
    case_id: UUID,
    body: PdfEvalRevisionRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Delete a case immediately.

    Args:
        case_id: Case identifier.
        body: Expected row version.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        Deleted case id.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        service.delete(caller, case_id, expected_row_version=body.expected_row_version)
    except Exception as exc:
        _raise_quiz(exc)
    return PdfEvalMutationResponse(
        case_id=case_id, row_version=body.expected_row_version
    )


@router.post("/drafts/regenerate", response_model=PdfEvalMutationResponse)
def regenerate_pdf_eval_drafts(
    body: PdfEvalRegenerateRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Insert generated-only rows from current authorized passages. Never self-approves.

    Args:
        body: Selected document.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        Inserted count.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        inserted = service.regenerate_drafts(caller, document_id=body.document_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except Exception as exc:
        _raise_quiz(exc)
    return PdfEvalMutationResponse(inserted_count=inserted)


@router.get("/passages", response_model=PdfEvalPassageListResponse)
def list_pdf_eval_passages(
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
    document_id: Annotated[UUID, Query()],
    after: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=60)] = 20,
    page_number: Annotated[int | None, Query(ge=1)] = None,
) -> PdfEvalPassageListResponse:
    """List ACL/current representative passages for one selected document.

    Args:
        caller: Authenticated caller.
        service: Workspace service.
        document_id: Caller-readable document.
        after: Keyset cursor.
        limit: Page size.
        page_number: Optional exact page filter.

    Returns:
        Authorized passages.
    """

    _require_owner_admin(caller)
    try:
        items = service.list_passages(
            caller,
            document_id=document_id,
            limit=limit,
            after_chunk_id=after,
            page_number=page_number,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except Exception as exc:
        _raise_quiz(exc)
    next_id = items[-1].chunk_id if len(items) == limit else None
    return PdfEvalPassageListResponse(
        items=[
            PdfEvalPassageResponse(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                version_id=item.version_id,
                page_number=item.page_number,
                heading_path=item.section_path,
                raw_text=item.raw_text,
            )
            for item in items
        ],
        next_chunk_id=next_id,
    )


@router.post(
    "/exams",
    response_model=PdfEvalExamAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_pdf_eval_exam(
    body: PdfEvalExamStartRequest,
    request: Request,
    caller: CallerContextDep,
    exams: Annotated[ExamRepository, Depends(get_exam_repository)],
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalExamAcceptedResponse | JSONResponse:
    """Enqueue a durable exam. The HTTP request never scores cases.

    Args:
        body: Split and idempotency key. Holdout is not an allowed split.
        request: Request for rate limits and supervisor bind.
        caller: Authenticated owner/admin.
        exams: Exam RPCs.
        service: Quiz status for empty-dataset counts.

    Returns:
        202 accepted or idempotent reconnect.
    """

    _require_owner_admin(caller)
    _rate_exam_mutation(request, caller)
    bind_exam_http_runtime(request.app, caller)
    fingerprint = capture_exam_candidate_fingerprint()
    if not fingerprint.complete or not fingerprint.digest:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="incomplete_fingerprint",
        )
    try:
        result = exams.enqueue(
            caller,
            split=body.split,
            idempotency_key=body.idempotency_key,
            candidate_fingerprint=fingerprint.digest,
            expected_dataset_hash=body.expected_dataset_hash,
        )
    except ExamRepositoryError as exc:
        if exc.code == "empty_dataset":
            counts = service.status(caller)
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "detail": "empty_dataset",
                    "draft_count": counts["draft_count"],
                    "approved_count": counts["approved_count"],
                    "rejected_count": counts["rejected_count"],
                    "stale_gold_count": counts["stale_gold_count"],
                    "live_count": counts["live_count"],
                },
            )
        _raise_exam(exc)
    return PdfEvalExamAcceptedResponse(
        exam_run_id=result.exam_run_id,
        status=result.status,
        dataset_hash=result.dataset_hash,
        replayed=result.replayed,
        holdout_opened=False,
    )


@router.get("/exams/{exam_run_id}", response_model=PdfEvalExamStatusResponse)
def get_pdf_eval_exam(
    exam_run_id: UUID,
    request: Request,
    caller: CallerContextDep,
    exams: Annotated[ExamRepository, Depends(get_exam_repository)],
) -> PdfEvalExamStatusResponse:
    """Poll one exam. Survives frontend refresh and API restart.

    Args:
        exam_run_id: Exam id.
        request: Request for rate limits and supervisor bind.
        caller: Authenticated owner/admin.
        exams: Exam RPCs.

    Returns:
        Count-only status.

    Raises:
        HTTPException: 404 when the exam is inaccessible.
    """

    _require_owner_admin(caller)
    _rate_exam_read(request, caller)
    bind_exam_http_runtime(request.app, caller)
    try:
        row = exams.get(caller, exam_run_id=exam_run_id)
    except Exception as exc:
        _raise_exam(exc)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return PdfEvalExamStatusResponse(
        exam_run_id=row.exam_run_id,
        split=row.split,
        status=row.status,
        dataset_hash=row.dataset_hash,
        case_count=row.case_count,
        completed_case_count=row.completed_case_count,
        holdout_opened=row.holdout_opened,
        candidate_fingerprint=row.candidate_fingerprint,
    )


@router.post("/exams/{exam_run_id}/cancel", response_model=PdfEvalExamStatusResponse)
def cancel_pdf_eval_exam(
    exam_run_id: UUID,
    request: Request,
    caller: CallerContextDep,
    exams: Annotated[ExamRepository, Depends(get_exam_repository)],
) -> PdfEvalExamStatusResponse:
    """Idempotently cancel a non-terminal exam.

    Args:
        exam_run_id: Exam id.
        request: Request for rate limits.
        caller: Authenticated owner/admin.
        exams: Exam RPCs.

    Returns:
        Status after cancel.
    """

    _require_owner_admin(caller)
    _rate_exam_mutation(request, caller)
    bind_exam_http_runtime(request.app, caller)
    try:
        exams.cancel(caller, exam_run_id=exam_run_id)
        row = exams.get(caller, exam_run_id=exam_run_id)
    except Exception as exc:
        _raise_exam(exc)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return PdfEvalExamStatusResponse(
        exam_run_id=row.exam_run_id,
        split=row.split,
        status=row.status,
        dataset_hash=row.dataset_hash,
        case_count=row.case_count,
        completed_case_count=row.completed_case_count,
        holdout_opened=row.holdout_opened,
        candidate_fingerprint=row.candidate_fingerprint,
    )


@router.get("/reports/latest", response_model=PdfEvalExamReportResponse)
def pdf_eval_latest_report(
    request: Request,
    caller: CallerContextDep,
    exams: Annotated[ExamRepository, Depends(get_exam_repository)],
    split: str = Query(pattern="^(development|qualification)$"),
) -> PdfEvalExamReportResponse:
    """Return the latest succeeded count-only report for one split.

    Args:
        request: Request for rate limits.
        caller: Authenticated owner/admin.
        exams: Exam RPCs.
        split: ``development`` or ``qualification``. Holdout is rejected.

    Returns:
        Count-only report or ``present=false``. Partial exams never appear.
    """

    _require_owner_admin(caller)
    _rate_exam_read(request, caller)
    try:
        report = exams.latest_report(caller, split=split)
    except Exception as exc:
        _raise_exam(exc)
    if report is None:
        return PdfEvalExamReportResponse(
            present=False, holdout_opened=False, split=split
        )
    return PdfEvalExamReportResponse(
        present=True,
        holdout_opened=report.holdout_opened,
        exam_run_id=report.exam_run_id,
        split=report.split,
        dataset_hash=report.dataset_hash,
        case_count=report.case_count,
        hit_count=report.hit_count,
        hybrid_recall_at_10=report.hybrid_recall_at_10,
        gates_pass=report.gates_pass,
        created_at=report.created_at,
    )


@router.get("/reports/{exam_run_id}/cases", response_model=PdfEvalExamCaseListResponse)
def list_pdf_eval_exam_cases(
    exam_run_id: UUID,
    request: Request,
    caller: CallerContextDep,
    exams: Annotated[ExamRepository, Depends(get_exam_repository)],
) -> PdfEvalExamCaseListResponse:
    """Return count-only report cases. Inaccessible reports are 404.

    Args:
        exam_run_id: Succeeded exam/report id.
        request: Request for rate limits.
        caller: Authenticated owner/admin.
        exams: Exam RPCs.

    Returns:
        Case rows with ``missed_count``.
    """

    _require_owner_admin(caller)
    _rate_exam_read(request, caller)
    try:
        items = exams.list_report_cases(caller, exam_run_id=exam_run_id)
    except Exception as exc:
        _raise_exam(exc)
    if not items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return PdfEvalExamCaseListResponse(
        exam_run_id=exam_run_id,
        items=[
            PdfEvalExamCaseResponse(
                case_id=item.case_id,
                ordinal=item.ordinal,
                hit=item.hit,
                gold_count=item.gold_count,
                ranked_hit_count=item.ranked_hit_count,
                latency_ms=item.latency_ms,
            )
            for item in items
        ],
        missed_count=sum(1 for item in items if not item.hit),
    )


@router.post("/cases/{case_id}/compare-run", response_model=PdfEvalCompareRunResponse)
def compare_pdf_eval_run(
    case_id: UUID,
    body: PdfEvalCompareRunRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalCompareRunResponse:
    """Compare a caller-owned run's ACL-rechecked citations to gold IDs.

    Args:
        case_id: Evaluation case.
        body: Run id.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        Count-only overlap. Manual AI test, not official Recall@10.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        payload = service.compare_run(caller, case_id=case_id, run_id=body.run_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except Exception as exc:
        _raise_quiz(exc)
    return PdfEvalCompareRunResponse.model_validate(payload)
