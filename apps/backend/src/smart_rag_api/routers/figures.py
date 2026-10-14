"""Authorized figure PNG download. No public object URLs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from smart_rag_core.query_admission.exceptions import QueryAdmissionError

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.figures_http import FigureHttpService, FigureReadError
from smart_rag_api.services.http_errors import raise_admission_http

router = APIRouter(prefix="/figures", tags=["figures"])


def get_figure_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> FigureHttpService:
    """Factory for figure reads.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Figure service.
    """

    return FigureHttpService(postgres_url)


@router.get("/{figure_key}")
def get_figure_png(
    request: Request,
    figure_key: str,
    caller: CallerContextDep,
    service: Annotated[FigureHttpService, Depends(get_figure_service)],
) -> Response:
    """Stream one figure PNG when the caller can read its document.

    Args:
        request: Active request.
        figure_key: Stable figure id from ingestion metadata.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        PNG bytes. The model never supplies this URL.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"figure-read:{caller.user_id}",
        kind=RateLimitKind.LOW_RISK_READ,
        max_attempts=120,
    )
    if not figure_key.isalnum() or len(figure_key) > 64:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        png = service.read_png(caller, figure_key)
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except FigureReadError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    if png is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return Response(content=png, media_type="image/png")
