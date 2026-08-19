"""Operations: liveness, dependency-aware readiness, and /api/meta."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from smart_rag_core.security.identity import UserRole
from smart_rag_core.settings import BackendSettings

from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.schemas.fastapi_security import MetaResponse
from smart_rag_api.services.readiness import (
    ReadinessResponse,
    build_readiness,
    public_readiness_as_dict,
    readiness_as_dict,
)

router = APIRouter(tags=["ops"])


def _build_request_readiness(request: Request) -> ReadinessResponse:
    """Compose readiness from lifespan-bound probes.

    Args:
        request: Request with lifespan state.

    Returns:
        Honest readiness model used by public and operator views.
    """

    settings: BackendSettings | None = getattr(request.app.state, "settings", None)
    return build_readiness(
        settings,
        valkey_limits=getattr(request.app.state, "valkey_limits_client", None),
        valkey_cache=getattr(request.app.state, "valkey_cache_client", None),
        lightrag_attached=getattr(request.app.state, "lightrag_adapter", None)
        is not None,
        rate_limit_degraded=bool(
            getattr(request.app.state, "rate_limit_degraded", False)
        ),
    )


@router.get("/health/live")
def live() -> dict[str, str]:
    """Process liveness. Does not probe dependencies.

    Returns:
        ``status=live``.
    """

    return {"status": "live"}


@router.get("/health/ready")
def ready(request: Request) -> dict[str, object]:
    """Unauthenticated readiness. Mock/graph-unconfigured is never query-ready.

    The public body is ``status``, ``query_ready``, and a coarse ``detail``.
    Named dependencies stay on ``GET /ops/ready``.

    Args:
        request: Request with lifespan state.

    Returns:
        Public readiness mapping without internal dependency names.
    """

    return public_readiness_as_dict(_build_request_readiness(request))


@router.get("/ops/ready")
def operator_ready(request: Request, caller: CallerContextDep) -> dict[str, object]:
    """Authenticated operator readiness with named dependency probes.

    Args:
        request: Request with lifespan state.
        caller: JWKS-verified caller. Owner or admin only.

    Returns:
        Full readiness mapping including named dependencies.

    Raises:
        HTTPException: 403 when the caller is not owner or admin.
    """

    if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    return readiness_as_dict(_build_request_readiness(request))


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
