"""Thin caller and company usage summary routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.schemas.fastapi_security import UsageResponse
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.feedback_usage import FeedbackUsageService
from smart_rag_api.services.http_errors import raise_admission_http

router = APIRouter(prefix="/usage", tags=["usage"])


def get_usage_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> FeedbackUsageService:
    """Factory for usage summaries.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Feedback/usage service.
    """

    return FeedbackUsageService(postgres_url)


@router.get("/me", response_model=UsageResponse)
def caller_usage_route(
    request: Request,
    caller: CallerContextDep,
    service: Annotated[FeedbackUsageService, Depends(get_usage_service)],
) -> UsageResponse:
    """Return the caller's usage totals. No prompt text.

    Args:
        request: Active request.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Caller usage summary.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"usage-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=60,
    )
    try:
        summary = service.caller_usage(caller)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return UsageResponse(
        scope=summary.scope,
        cost_usd=summary.cost_usd,
        cost_reporting=summary.cost_reporting,
        checkpoint_usage=summary.checkpoint_usage,
        display_cost_usd=summary.display_cost_usd,
        prompt_tokens=summary.prompt_tokens,
        completion_tokens=summary.completion_tokens,
        usage_rows=summary.usage_rows,
    )


@router.get("/company", response_model=UsageResponse)
def company_usage_route(
    request: Request,
    caller: CallerContextDep,
    service: Annotated[FeedbackUsageService, Depends(get_usage_service)],
) -> UsageResponse:
    """Return company totals. Owner/admin only.

    Args:
        request: Active request.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Company usage summary.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"usage-company:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=60,
    )
    try:
        summary = service.company_usage(caller)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return UsageResponse(
        scope=summary.scope,
        cost_usd=summary.cost_usd,
        cost_reporting=summary.cost_reporting,
        checkpoint_usage=summary.checkpoint_usage,
        display_cost_usd=summary.display_cost_usd,
        prompt_tokens=summary.prompt_tokens,
        completion_tokens=summary.completion_tokens,
        usage_rows=summary.usage_rows,
    )
