"""Ingestion lifecycle status and safe retry routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import UserRole

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.schemas.ingestion_status import (
    DocumentIngestionStatusResponse,
    RetryIngestionJobResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.http_errors import raise_admission_http
from smart_rag_api.services.ingestion_status_http import (
    IngestionStatusHttpService,
    JobNotFoundError,
    JobRepositoryError,
    JobRetryNotAllowedError,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def get_ingestion_status_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> IngestionStatusHttpService:
    """Factory for ingestion status HTTP operations.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Ingestion status service.
    """

    return IngestionStatusHttpService(postgres_url)


@router.get(
    "/versions/{version_id}/status",
    response_model=DocumentIngestionStatusResponse,
)
def get_version_ingestion_status(
    version_id: UUID,
    caller: CallerContextDep,
    service: Annotated[
        IngestionStatusHttpService, Depends(get_ingestion_status_service)
    ],
) -> DocumentIngestionStatusResponse:
    """Return public lifecycle and nested diagnostics for one document version.

    Args:
        version_id: Canonical document version identifier.
        caller: Authenticated caller. Unauthorized versions return 404.
        service: Injected status service.

    Returns:
        Version status plus recent job summaries.

    Raises:
        HTTPException: 404 when the version is missing or unauthorized.
    """

    try:
        return service.get_version_status(caller, version_id=version_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=RetryIngestionJobResponse,
)
def retry_ingestion_job(
    request: Request,
    job_id: UUID,
    caller: CallerContextDep,
    service: Annotated[
        IngestionStatusHttpService, Depends(get_ingestion_status_service)
    ],
) -> RetryIngestionJobResponse:
    """Retry one failed, backoff, or dead-letter ingestion job when authorized.

    Dead-letter replay creates a **new** job with a new idempotency key and
    retains the original dead-letter row. Failed-but-not-dead-letter jobs only
    clear ``next_attempt_at``; ``last_error`` and ``attempt_count`` stay.

    Args:
        request: FastAPI request for rate limits.
        job_id: Source ingestion job identifier.
        caller: Authenticated caller context.
        service: Injected status service.

    Returns:
        The job that should run next (replay child for dead-letter).

    Raises:
        HTTPException: 403 for members/viewers, 404 when missing, 409 when the
            job is not retryable.
    """

    try:
        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
        enforce_rate_limit(
            request,
            bucket_key=f"ingestion-retry:{caller.user_id}",
            kind=RateLimitKind.COST_MUTATION,
            max_attempts=20,
        )
        return service.retry_job(caller, job_id=job_id)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not_found",
        ) from exc
    except (JobRetryNotAllowedError, JobRepositoryError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="retry_not_allowed",
        ) from exc
