"""Owner/admin website crawl enqueue route."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from smart_rag_core.security.identity import UserRole
from smart_rag_core.settings import BackendSettings

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit
from smart_rag_api.schemas.ingestion_crawl import (
    EnqueueWebsiteCrawlRequest,
    EnqueueWebsiteCrawlResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.crawl_enqueue import (
    CrawlEnqueueError,
    enqueue_approved_website_crawl,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post(
    "/crawls",
    response_model=EnqueueWebsiteCrawlResponse,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_website_crawl(
    request: Request,
    body: EnqueueWebsiteCrawlRequest,
    caller: CallerContextDep,
) -> EnqueueWebsiteCrawlResponse:
    """Enqueue one approved website crawl. Members cannot broaden crawl scope.

    Args:
        request: FastAPI request with backend settings.
        body: Start URL, approved domain, and crawl bounds.
        caller: Authenticated caller context.

    Returns:
        Document/source/job identifiers. Duplicate idempotency keys reuse one job.

    Raises:
        HTTPException: 403 for members/viewers, 400 for policy/domain mismatch,
            503 when the database URL is unset.
    """

    if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    enforce_rate_limit(
        request,
        bucket_key=f"crawl-start:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=10,
    )
    settings: BackendSettings = request.app.state.settings
    if settings.supabase_db_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unconfigured",
        )
    try:
        outcome = enqueue_approved_website_crawl(
            settings.supabase_db_url.get_secret_value(),
            caller_user_id=UUID(caller.user_id),
            caller_role=caller.role.value,
            caller_authorization_version=caller.authorization_version,
            start_url=body.start_url,
            approved_domain=body.approved_domain,
            idempotency_key=body.idempotency_key,
            document_title=body.document_title,
            max_depth=body.max_depth,
            max_pages=body.max_pages,
            content_class=body.content_class,
            graph_eligible=body.graph_eligible,
            attestation_policy_version=body.attestation_policy_version,
        )
    except CrawlEnqueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="crawl_enqueue_rejected",
        ) from exc
    return EnqueueWebsiteCrawlResponse(
        document_id=outcome.document_id,
        version_id=outcome.version_id,
        source_id=outcome.source_id,
        approval_id=outcome.approval_id,
        job_id=outcome.job_id,
    )
