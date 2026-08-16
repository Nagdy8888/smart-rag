"""Authenticated graph inspection route."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request, status
from smart_rag_core.retrieval.graph import INSPECTION_DEADLINE_SECONDS
from smart_rag_core.retrieval.graph_retriever import GraphQueryError
from smart_rag_core.settings import BackendSettings

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.schemas.graph_inspect import (
    GraphInspectRequest,
    GraphInspectResponse,
)
from smart_rag_api.services.graph_inspect import inspect_graph_for_caller

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
