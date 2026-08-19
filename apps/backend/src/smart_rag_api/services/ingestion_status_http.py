"""Ingestion lifecycle status and retry HTTP wrappers. No router SQL."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import psycopg
from smart_rag_core.jobs.dead_letter import DeadLetterService
from smart_rag_core.jobs.exceptions import (
    JobNotFoundError,
    JobRepositoryError,
    JobRetryNotAllowedError,
)
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.repositories.ingestion_status import IngestionStatusRepository
from smart_rag_core.security.identity import CallerContext, UserRole

from smart_rag_api.schemas.ingestion_status import (
    DocumentIngestionStatusResponse,
    IngestionJobSummary,
    IngestionStatusResponse,
    RetryIngestionJobResponse,
)
from smart_rag_api.services.ingestion_error_text import sanitize_ingestion_last_error


class IngestionStatusHttpService:
    """Factory-injected ingestion status and retry operations."""

    def __init__(self, postgres_url: str) -> None:
        """Store the app_api DSN.

        Args:
            postgres_url: Postgres URL used with ``SET ROLE app_api``.
        """

        self._postgres_url = postgres_url

    def get_version_status(
        self,
        caller: CallerContext,
        *,
        version_id: UUID,
    ) -> DocumentIngestionStatusResponse:
        """Return ACL-visible lifecycle diagnostics for one version.

        Args:
            caller: Authenticated caller. Unauthorized versions look missing.
            version_id: Canonical document version identifier.

        Returns:
            Version status plus recent job summaries. ``last_error`` is sanitized.

        Raises:
            QueryAdmissionError: ``not_found`` when missing or unauthorized.
        """

        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            repository = IngestionStatusRepository(connection)
            row = repository.get_version_status(
                version_id,
                caller_user_id=caller.user_id,
                caller_role=caller.rpc_role(),
                caller_authorization_version=caller.rpc_authorization_version(),
            )
        if row is None:
            raise QueryAdmissionError("not_found")
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
        jobs_raw = payload.pop("recent_jobs", [])
        version = IngestionStatusResponse.model_validate(payload)
        return DocumentIngestionStatusResponse(
            version=version,
            recent_jobs=[_job_summary(job) for job in _as_job_list(jobs_raw)],
        )

    def retry_job(
        self,
        caller: CallerContext,
        *,
        job_id: UUID,
    ) -> RetryIngestionJobResponse:
        """Retry one failed, backoff, or dead-letter ingestion job.

        Args:
            caller: Authenticated caller. Owner/admin only.
            job_id: Source ingestion job identifier.

        Returns:
            The job that should run next (replay child for dead-letter).

        Raises:
            QueryAdmissionError: ``forbidden`` for members/viewers.
            JobNotFoundError: When the job is missing.
            JobRetryNotAllowedError: When the job is not retryable.
            JobRepositoryError: When the retry RPC fails.

        Side Effects:
            Dead-letter replay inserts a new pending job. Failed jobs only
            clear ``next_attempt_at``.
        """

        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute("SET ROLE app_api")
            service = DeadLetterService(connection)
            result = service.retry_ingestion(job_id)
            connection.commit()
        return RetryIngestionJobResponse(
            job_id=result.job.id,
            status=result.job.status.value,
            detail=result.detail,
        )


def _as_job_list(value: object) -> list[object]:
    """Coerce a JSON jobs payload to a list.

    Args:
        value: RPC ``recent_jobs`` value.

    Returns:
        List of job mappings.
    """

    if isinstance(value, list):
        return value
    return []


def _job_summary(job: object) -> IngestionJobSummary:
    """Map one job mapping to the HTTP schema with a sanitized error.

    Args:
        job: JSON object from the status RPC.

    Returns:
        Job summary.

    Raises:
        QueryAdmissionError: When the payload is not an object.
    """

    if not isinstance(job, dict):
        raise QueryAdmissionError("not_found")
    mapped = cast(dict[str, Any], job)
    category = mapped.get("error_category")
    category_text = str(category) if category is not None else None
    raw_error = mapped.get("last_error")
    mapped["last_error"] = sanitize_ingestion_last_error(
        str(raw_error) if raw_error is not None else None,
        category=category_text,
    )
    return IngestionJobSummary.model_validate(mapped)


__all__ = [
    "IngestionStatusHttpService",
    "JobNotFoundError",
    "JobRepositoryError",
    "JobRetryNotAllowedError",
]
