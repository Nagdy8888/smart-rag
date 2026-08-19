"""Authenticated graph inspection route."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.retrieval.graph import INSPECTION_DEADLINE_SECONDS
from smart_rag_core.retrieval.graph_retriever import GraphQueryError
from smart_rag_core.settings import BackendSettings

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit
from smart_rag_api.schemas.fastapi_security import GraphEntityResponse
from smart_rag_api.schemas.graph_inspect import (
    GraphInspectRequest,
    GraphInspectResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.graph_entities import GraphEntityService
from smart_rag_api.services.graph_inspect import inspect_graph_for_caller
from smart_rag_api.services.http_errors import raise_admission_http

router = APIRouter(prefix="/graph", tags=["graph"])


def _postgres_url(request: Request) -> str:
    """Return the backend Postgres URL or fail closed.

    Args:
        request: FastAPI request with startup settings.

    Returns:
        Database URL string.

    Raises:
        HTTPException: 503 when the database URL is unset.
    """

    settings: BackendSettings = request.app.state.settings
    if settings.supabase_db_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unconfigured",
        )
    return settings.supabase_db_url.get_secret_value()


@router.post("/inspect", response_model=GraphInspectResponse)
def inspect_graph_route(
    request: Request,
    body: GraphInspectRequest,
    caller: CallerContextDep,
) -> GraphInspectResponse:
    """Inspect authorized graph objects. Members and viewers are ACL-filtered.

    FastAPI applies ``COST_MUTATION`` rate limits here. Pre-auth IP limits
    also cover ``POST /graph/*`` via ``_MUTATION_PREFIXES`` (GET search is
    skipped because this middleware ignores GET/HEAD/OPTIONS).

    Args:
        request: FastAPI request with backend settings.
        body: Seed entity keys and/or document id, depth at most 3.
        caller: Authenticated caller context.

    Returns:
        At most 200 rows and canonical locators. Native prose is omitted.

    Raises:
        HTTPException: 401 via identity dependency, 400 for seed/deadline,
            503 when the database URL is unset.
    """

    started = time.monotonic()
    enforce_rate_limit(
        request,
        bucket_key=f"graph-inspect:{caller.user_id}",
        kind=RateLimitKind.COST_MUTATION,
        max_attempts=20,
    )
    remaining = INSPECTION_DEADLINE_SECONDS - (time.monotonic() - started)
    try:
        return inspect_graph_for_caller(
            _postgres_url(request),
            caller=caller,
            body=body,
            remaining_deadline_seconds=remaining,
        )
    except GraphQueryError as exc:
        detail = exc.reason
        if detail in {"graph_deadline", "inspect_seed_exceeds_limit"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="inspect_rejected",
        ) from exc


@router.get("/entities/search", response_model=list[GraphEntityResponse])
def search_graph_entities_route(
    request: Request,
    caller: CallerContextDep,
    q: Annotated[str, Query(min_length=1, max_length=128)],
    limit: Annotated[int, Query(ge=1, le=25)] = 25,
) -> list[GraphEntityResponse]:
    """Search authorized entity ids. No vendor prose.

    Args:
        request: FastAPI request with backend settings.
        caller: Authenticated caller.
        q: Bounded search string.
        limit: Max 25 matches.

    Returns:
        ACL-filtered entity hits with escaped object ids.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"graph-search:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    service = GraphEntityService(_postgres_url(request))
    try:
        matches = service.search(caller, query=q, limit=limit)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return [
        GraphEntityResponse(
            object_id=item.object_id,
            object_type=item.object_type,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            version_id=item.version_id,
            support=item.support,
        )
        for item in matches
    ]
