"""Reject incompatible clients before query-run reservation."""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from smart_rag_core.settings import BackendSettings
from smart_rag_core.sse.handshake import client_version_is_supported


class ClientVersionUnsupportedError(Exception):
    """Raised when ``X-Client-Version`` is missing or below minimum.

    Attributes:
        min_client_version: Published minimum.
        sse_schema_version: Published SSE schema.
    """

    def __init__(self, *, min_client_version: str, sse_schema_version: str) -> None:
        """Store published versions for the 426 body.

        Args:
            min_client_version: Minimum supported client version.
            sse_schema_version: Current SSE schema version.
        """

        super().__init__("client_version_unsupported")
        self.min_client_version = min_client_version
        self.sse_schema_version = sse_schema_version


def enforce_client_handshake(request: Request, client_version: str | None) -> None:
    """Fail closed before admit when the client version is unsupported.

    Args:
        request: Request with lifespan settings.
        client_version: ``X-Client-Version`` header.

    Raises:
        ClientVersionUnsupportedError: Missing or below-minimum version.
        HTTPException: 503 when settings were not bound.
    """

    settings: BackendSettings | None = getattr(request.app.state, "settings", None)
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="settings_unconfigured",
        )
    if client_version_is_supported(client_version, settings.min_client_version):
        return
    raise ClientVersionUnsupportedError(
        min_client_version=settings.min_client_version,
        sse_schema_version=settings.sse_schema_version,
    )
