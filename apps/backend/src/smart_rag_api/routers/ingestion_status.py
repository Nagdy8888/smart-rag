"""Ingestion lifecycle status and safe retry routes."""

from __future__ import annotations

from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Request, status
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
    """Return public lifecycle and diagnostics for one document version."""

    settings: BackendSettings = request.app.state.settings
    _ = caller
    with psycopg.connect(_postgres_url(settings)) as connection:
        connection.execute("SET ROLE app_api")
        repository = IngestionStatusRepository(connection)
        row = repository.get_version_status(version_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
        jobs = repository.list_recent_jobs(document_id=UUID(str(row["document_id"])))
    retry_allowed = caller.role in {UserRole.OWNER, UserRole.ADMIN}
    version = IngestionStatusResponse(
        **row,
        retry_allowed=retry_allowed,
    )
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
    """Retry one failed or dead-letter ingestion job when authorized."""

    if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    settings: BackendSettings = request.app.state.settings
    with psycopg.connect(_postgres_url(settings)) as connection:
        connection.execute("SET ROLE app_api")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE app.ingestion_jobs
                SET
                  status = 'pending',
                  attempt_count = 0,
                  next_attempt_at = NULL,
                  last_error = NULL,
                  error_category = NULL,
                  updated_at = timezone('utc', now())
                WHERE id = %s
                  AND status IN ('failed', 'dead_letter')
                RETURNING id, status
                """,
                (job_id,),
            )
            row = cursor.fetchone()
            connection.commit()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="retry_not_allowed",
        )
    return RetryIngestionJobResponse(
        job_id=job_id,
        status=str(row[1]),
        detail="job requeued",
    )
