"""Local-only owner/admin PDF evaluation workspace routes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from smart_rag_core.evaluation.holdout import HoldoutSealedError
from smart_rag_core.evaluation.private_pdf.schema import PrivatePdfLabeledCase
from smart_rag_core.evaluation.private_pdf.workspace_models import (
    WorkspaceBoundsError,
    WorkspaceCasePatch,
    WorkspacePathRejected,
    WorkspaceRevisionConflict,
)
from smart_rag_core.evaluation.private_pdf.workspace_store import PdfEvalWorkspaceStore
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import UserRole
from smart_rag_core.settings import BackendSettings, Environment

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.routers.query_runs import get_query_run_service
from smart_rag_api.schemas.pdf_eval import (
    PdfEvalCaseDetailResponse,
    PdfEvalCaseListResponse,
    PdfEvalCasePatchRequest,
    PdfEvalCaseSummaryResponse,
    PdfEvalCompareRunRequest,
    PdfEvalCompareRunResponse,
    PdfEvalMutationResponse,
    PdfEvalPassageListResponse,
    PdfEvalPassageResponse,
    PdfEvalReportResponse,
    PdfEvalRevisionRequest,
    PdfEvalStatusResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.pdf_eval_workspace import PdfEvalWorkspaceService
from smart_rag_api.services.query_runs import QueryRunService

router = APIRouter(prefix="/admin/pdf-eval", tags=["pdf-eval"])


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
    try:
        store = PdfEvalWorkspaceStore(Path(settings.pdf_eval_workspace_root))
    except (WorkspacePathRejected, HoldoutSealedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_found"
        ) from exc
    return PdfEvalWorkspaceService(
        store,
        postgres_url=postgres_url,
        query_runs=query_runs,
    )


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


def _map_store_error(exc: Exception) -> NoReturn:
    """Raise the matching HTTP error for a store failure.

    Args:
        exc: Store or path exception.

    Raises:
        HTTPException: Mapped status.
    """

    if isinstance(exc, WorkspaceRevisionConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="stale_workspace_revision",
        ) from exc
    if isinstance(exc, WorkspacePathRejected | HoldoutSealedError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_found"
        ) from exc
    if isinstance(exc, WorkspaceBoundsError | ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    if isinstance(exc, FileNotFoundError | KeyError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_found"
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="request_rejected",
    ) from exc


def _summary(case: PrivatePdfLabeledCase) -> PdfEvalCaseSummaryResponse:
    """Build a list row without private question fields.

    Args:
        case: Labeled case.

    Returns:
        Summary response.
    """

    return PdfEvalCaseSummaryResponse(
        case_id=case.meta.case_id,
        split=case.meta.split,
        query_class=case.meta.query_class,
        human_approved=case.meta.human_approved,
        generated_only=case.meta.generated_only,
        reviewer=case.meta.reviewer,
        expected_refusal=case.meta.expected_refusal,
        gold_chunk_count=len(case.meta.chunk_ids),
    )


def _detail(revision: str, case: PrivatePdfLabeledCase) -> PdfEvalCaseDetailResponse:
    """Build a case detail body.

    Args:
        revision: Dataset SHA-256.
        case: Labeled case.

    Returns:
        Detail response.
    """

    return PdfEvalCaseDetailResponse(
        revision=revision,
        case_id=case.meta.case_id,
        split=case.meta.split,
        query_class=case.meta.query_class,
        human_approved=case.meta.human_approved,
        generated_only=case.meta.generated_only,
        reviewer=case.meta.reviewer,
        expected_refusal=case.meta.expected_refusal,
        expected_scope=case.meta.expected_scope,
        chunk_ids=case.meta.chunk_ids,
        page_numbers=case.meta.page_numbers,
        heading_paths=case.meta.heading_paths,
        required_terms=case.meta.required_terms,
        question=case.question,
        expected_answer=case.expected_answer,
        atomic_facts=case.atomic_facts,
    )


@router.get("/status", response_model=PdfEvalStatusResponse)
def pdf_eval_status(
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalStatusResponse:
    """Return workspace status. Disabled mode is 404, not an empty dataset.

    Args:
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        Status without questions or filesystem paths.
    """

    _require_owner_admin(caller)
    try:
        payload = service.status()
    except Exception as exc:
        _map_store_error(exc)
    return PdfEvalStatusResponse.model_validate(payload)


@router.get("/cases", response_model=PdfEvalCaseListResponse)
def list_pdf_eval_cases(
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
    split: Annotated[str | None, Query(max_length=32)] = None,
    after: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=60)] = 20,
) -> PdfEvalCaseListResponse:
    """List case summaries without bulk question fields.

    Args:
        caller: Authenticated caller.
        service: Workspace service.
        split: Optional split filter. ``holdout`` is rejected.
        after: Keyset cursor.
        limit: Page size.

    Returns:
        Summaries and revision.
    """

    _require_owner_admin(caller)
    try:
        revision, cases, next_id = service.list_cases(
            split=split,
            after_case_id=after,
            limit=limit,
        )
    except Exception as exc:
        _map_store_error(exc)
    return PdfEvalCaseListResponse(
        revision=revision,
        items=[_summary(case) for case in cases],
        next_case_id=next_id,
    )


@router.get("/cases/{case_id}", response_model=PdfEvalCaseDetailResponse)
def get_pdf_eval_case(
    case_id: str,
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
        revision, case = service.get_case(case_id)
    except Exception as exc:
        _map_store_error(exc)
    return _detail(revision, case)


@router.patch("/cases/{case_id}", response_model=PdfEvalMutationResponse)
def patch_pdf_eval_case(
    case_id: str,
    body: PdfEvalCasePatchRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Edit editable fields. Cannot set reviewer, approval, split, or actor.

    Args:
        case_id: Case identifier.
        body: Patch plus expected revision.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        New revision.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    patch = WorkspaceCasePatch(
        question=body.question,
        expected_answer=body.expected_answer,
        atomic_facts=body.atomic_facts,
        chunk_ids=body.chunk_ids,
        page_numbers=body.page_numbers,
        heading_paths=body.heading_paths,
        required_terms=body.required_terms,
        expected_scope=body.expected_scope,
        expected_refusal=body.expected_refusal,
        query_class=body.query_class,
    )
    try:
        revision = service.patch_case(
            case_id,
            patch,
            expected_revision=body.expected_revision,
        )
    except Exception as exc:
        _map_store_error(exc)
    return PdfEvalMutationResponse(revision=revision, case_id=case_id)


@router.post("/cases/{case_id}/approve", response_model=PdfEvalMutationResponse)
def approve_pdf_eval_case(
    case_id: str,
    body: PdfEvalRevisionRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Approve a case. Reviewer is ``caller.user_id``.

    Args:
        case_id: Case identifier.
        body: Expected revision.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        New revision.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    if body.expected_revision is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="expected_revision"
        )
    try:
        revision = service.set_approval(
            case_id,
            approved=True,
            reviewer=caller.user_id,
            expected_revision=body.expected_revision,
        )
    except Exception as exc:
        _map_store_error(exc)
    return PdfEvalMutationResponse(revision=revision, case_id=case_id)


@router.post("/cases/{case_id}/reject", response_model=PdfEvalMutationResponse)
def reject_pdf_eval_case(
    case_id: str,
    body: PdfEvalRevisionRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Reject a case after named-human inspection.

    Args:
        case_id: Case identifier.
        body: Expected revision.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        New revision.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    if body.expected_revision is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="expected_revision"
        )
    try:
        revision = service.set_approval(
            case_id,
            approved=False,
            reviewer=caller.user_id,
            expected_revision=body.expected_revision,
        )
    except Exception as exc:
        _map_store_error(exc)
    return PdfEvalMutationResponse(revision=revision, case_id=case_id)


@router.post("/drafts/regenerate", response_model=PdfEvalMutationResponse)
def regenerate_pdf_eval_drafts(
    body: PdfEvalRevisionRequest,
    request: Request,
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalMutationResponse:
    """Replace drafts from current authorized passages. Never self-approves.

    Args:
        body: Expected revision, or None to create the file.
        request: Request for rate limits.
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        New revision.
    """

    _require_owner_admin(caller)
    _rate_admin_mutation(request, caller)
    try:
        revision = service.regenerate_drafts(
            caller,
            expected_revision=body.expected_revision,
        )
    except Exception as exc:
        _map_store_error(exc)
    return PdfEvalMutationResponse(revision=revision)


@router.get("/passages", response_model=PdfEvalPassageListResponse)
def list_pdf_eval_passages(
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
    after: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=60)] = 20,
) -> PdfEvalPassageListResponse:
    """List ACL/current representative passages for the workspace version.

    Args:
        caller: Authenticated caller.
        service: Workspace service.
        after: Keyset cursor.
        limit: Page size.

    Returns:
        Authorized passages.
    """

    _require_owner_admin(caller)
    try:
        items = service.list_passages(caller, limit=limit, after_chunk_id=after)
    except Exception as exc:
        _map_store_error(exc)
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


@router.get("/reports/latest", response_model=PdfEvalReportResponse)
def pdf_eval_latest_report(
    caller: CallerContextDep,
    service: Annotated[PdfEvalWorkspaceService, Depends(get_pdf_eval_service)],
) -> PdfEvalReportResponse:
    """Return the latest count-only report. Official Recall@10 stays CLI.

    Args:
        caller: Authenticated caller.
        service: Workspace service.

    Returns:
        Count-only report or ``present=false``.
    """

    _require_owner_admin(caller)
    try:
        payload = service.latest_report()
    except Exception as exc:
        _map_store_error(exc)
    return PdfEvalReportResponse.model_validate(payload)


@router.post("/cases/{case_id}/compare-run", response_model=PdfEvalCompareRunResponse)
def compare_pdf_eval_run(
    case_id: str,
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
        _map_store_error(exc)
    return PdfEvalCompareRunResponse.model_validate(payload)
