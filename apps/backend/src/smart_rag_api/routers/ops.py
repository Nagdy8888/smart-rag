"""Operations: liveness, dependency-aware readiness, and /api/meta."""

from __future__ import annotations

from fastapi import APIRouter, Request
from smart_rag_core.settings import BackendSettings

from smart_rag_api.schemas.fastapi_security import MetaResponse
from smart_rag_api.services.readiness import build_readiness, readiness_as_dict

router = APIRouter(tags=["ops"])


@router.get("/health/live")
def live() -> dict[str, str]:
    """Process liveness. Does not probe dependencies.

    Returns:
        ``status=live``.
    """

    return {"status": "live"}


@router.get("/health/ready")
def ready(request: Request) -> dict[str, object]:
    """Dependency-aware readiness. Mock/graph-unconfigured is never query-ready.

    Args:
        request: Request with lifespan state.

    Returns:
        Honest readiness mapping.
    """

    settings: BackendSettings | None = getattr(request.app.state, "settings", None)
    payload = build_readiness(
        settings,
        valkey_limits=getattr(request.app.state, "valkey_limits_client", None),
        valkey_cache=getattr(request.app.state, "valkey_cache_client", None),
        lightrag_attached=getattr(request.app.state, "lightrag_adapter", None)
        is not None,
        rate_limit_degraded=bool(
            getattr(request.app.state, "rate_limit_degraded", False)
        ),
    )
    return readiness_as_dict(payload)


@router.get("/api/meta", response_model=MetaResponse)
def api_meta(request: Request) -> MetaResponse:
    """Publish version handshake fields. Packet 6 owns enforcement.

    Args:
        request: Request with settings.

    Returns:
        api_version, sse_schema_version, min_client_version.
    """

    settings: BackendSettings | None = getattr(request.app.state, "settings", None)
    if settings is None:
        return MetaResponse(
            api_version="0.1.0",
            sse_schema_version="1",
            min_client_version="0.1.0",
        )
    return MetaResponse(
        api_version=settings.api_version,
        sse_schema_version=settings.sse_schema_version,
        min_client_version=settings.min_client_version,
    )
