"""Ingestion lifecycle status and safe retry routes."""

from __future__ import annotations

from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Request, status
from smart_rag_core.jobs.dead_letter import DeadLetterService
from smart_rag_core.jobs.exceptions import (
    JobNotFoundError,
    JobRepositoryError,
    JobRetryNotAllowedError,
)
from smart_rag_core.repositories.ingestion_status import IngestionStatusRepository
from smart_rag_core.security.identity import UserRole
from smart_rag_core.settings import BackendSettings

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.schemas.ingestion_status import (
    DocumentIngestionStatusResponse,
    IngestionJobSummary,
    IngestionStatusResponse,
    RetryIngestionJobResponse,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _postgres_url(settings: BackendSettings) -> str:
    """Return the configured Postgres URL or fail closed as unconfigured.

    Args:
        settings: Backend settings for this process.

    Returns:
        Postgres connection URL.

    Raises:
        HTTPException: When ``supabase_db_url`` is missing (HTTP 503).
    """

    if settings.supabase_db_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unconfigured",
        )
    return settings.supabase_db_url.get_secret_value()


@router.get(
    "/versions/{version_id}/status",
    response_model=DocumentIngestionStatusResponse,
)
def get_version_ingestion_status(
    request: Request,
    version_id: UUID,
    caller: CallerContextDep,
) -> DocumentIngestionStatusResponse:
    """Return public lifecycle and nested diagnostics for one document version.

    Args:
        request: FastAPI request with backend settings.
        version_id: Canonical document version identifier.
        caller: Authenticated caller; role controls ``retry_allowed`` only.

    Returns:
        Version status plus recent job summaries.

    Raises:
        HTTPException: 404 when the version is missing; 503 when the database
            URL is unset.
    """

    settings: BackendSettings = request.app.state.settings
    _ = caller
    with psycopg.connect(_postgres_url(settings)) as connection:
        connection.execute("SET ROLE app_api")
        repository = IngestionStatusRepository(connection)
        row = repository.get_version_status(version_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not_found"
            )
        jobs = repository.list_recent_jobs(document_id=UUID(str(row["document_id"])))
    retry_allowed = caller.role in {UserRole.OWNER, UserRole.ADMIN}
    payload = dict(row)
    payload["retry_allowed"] = retry_allowed
    for nested in (
        "scan",
        "review",
        "ocr",
        "chunks_tables",
        "embedding",
        "bm25",
        "queue_age",
        "graph_handoff",
    ):
        if payload.get(nested) is None:
            payload.pop(nested, None)
    version = IngestionStatusResponse.model_validate(payload)
    return DocumentIngestionStatusResponse(
        version=version,
        recent_jobs=[IngestionJobSummary(**job) for job in jobs],
    )


@router.post(
    "/jobs/{job_id}/retry",
    response_model=RetryIngestionJobResponse,
)
def retry_ingestion_job(
    request: Request,
    job_id: UUID,
    caller: CallerContextDep,
) -> RetryIngestionJobResponse:
    """Retry one failed, backoff, or dead-letter ingestion job when authorized.

    Dead-letter replay creates a **new** job with a new idempotency key and
    retains the original dead-letter row. Failed-but-not-dead-letter jobs only
    clear ``next_attempt_at``; ``last_error`` and ``attempt_count`` stay.

    Args:
        request: FastAPI request with backend settings.
        job_id: Source ingestion job identifier.
        caller: Authenticated caller context.

    Returns:
        The job that should run next (replay child for dead-letter).

    Raises:
        HTTPException: 403 for members/viewers, 404 when missing, 409 when the
            job is not retryable, 503 when the database URL is unset.
    """

    if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    settings: BackendSettings = request.app.state.settings
    with psycopg.connect(_postgres_url(settings)) as connection:
        connection.execute("SET ROLE app_api")
        service = DeadLetterService(connection)
        try:
            result = service.retry_ingestion(job_id)
        except JobNotFoundError as exc:
            connection.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="not_found",
            ) from exc
        except JobRetryNotAllowedError as exc:
            connection.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="retry_not_allowed",
            ) from exc
        except JobRepositoryError as exc:
            connection.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="retry_not_allowed",
            ) from exc
        connection.commit()
    return RetryIngestionJobResponse(
        job_id=result.job.id,
        status=result.job.status.value,
        detail=result.detail,
    )
