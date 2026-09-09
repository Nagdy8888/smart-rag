"""Owner/admin detector-finding review route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import UserRole

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.schemas.governance_reviews import (
    DetectorFindingReviewRequest,
    DetectorFindingReviewResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.governance_reviews_http import GovernanceReviewHttpService
from smart_rag_api.services.http_errors import raise_admission_http

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def get_governance_review_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> GovernanceReviewHttpService:
    """Factory for detector-review HTTP operations.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Review service.
    """

    return GovernanceReviewHttpService(postgres_url)


@router.post(
    "/detector-findings/reviews",
    response_model=DetectorFindingReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def review_detector_finding(
    request: Request,
    body: DetectorFindingReviewRequest,
    caller: CallerContextDep,
    service: Annotated[
        GovernanceReviewHttpService, Depends(get_governance_review_service)
    ],
) -> DetectorFindingReviewResponse:
    """Record an owner/admin hash-bound detector review.

    Clients cannot submit detector outcomes. Unauthorized callers receive
    the same 404 as a missing finding.

    Args:
        request: FastAPI request for rate limiting.
        body: Finding id, decision, reason, and idempotency key.
        caller: Authenticated caller.
        service: Injected review service.

    Returns:
        Review identifiers. Duplicate idempotency keys replay.

    Raises:
        HTTPException: 404 when unauthorized or missing; 429 when limited.
    """

    if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
        raise_admission_http(QueryAdmissionError("not_found"))
    enforce_rate_limit(
        request,
        bucket_key=f"detector-review:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=20,
    )
    try:
        review_id, finding_id, decision, replayed = service.review_finding(
            caller,
            finding_id=body.finding_id,
            decision=body.decision,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    del request
    return DetectorFindingReviewResponse(
        review_id=review_id,
        finding_id=finding_id,
        decision=decision,
        replayed=replayed,
    )
