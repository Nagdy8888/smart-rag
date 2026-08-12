"""FastAPI dependency stub for server-derived caller identity (Packet 3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from smart_rag_core.security.identity import CallerContext, UserRole

_AUTHORIZATION_VERSION_HEADER = "X-Authorization-Version"


async def resolve_caller_context(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    x_authorization_version: Annotated[
        int | None, Header(alias=_AUTHORIZATION_VERSION_HEADER)
    ] = None,
) -> CallerContext:
    """Resolve typed caller context for downstream RPC binding.

    Packet 3 stub: headers simulate server-side JWT + profile resolution.
    Packet 4 replaces this with JWKS verification and live profile reads.
    Headers are accepted only in local development; production wiring must
    derive every field from verified auth without trusting client metadata.

    Args:
        x_user_id: Development-only subject UUID header.
        x_user_role: Development-only role header matching ``app.profiles.role``.
        x_authorization_version: Development-only authorization snapshot header.

    Returns:
        Frozen ``CallerContext`` for RPC argument binding.

    Raises:
        HTTPException: When required identity fields are missing or invalid.
    """

    if x_user_id is None or x_user_role is None or x_authorization_version is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing server-derived caller context",
        )

    try:
        role = UserRole(x_user_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid caller role",
        ) from exc

    if x_authorization_version < 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authorization version",
        )

    return CallerContext(
        user_id=x_user_id,
        role=role,
        authorization_version=x_authorization_version,
    )


CallerContextDep = Annotated[CallerContext, Depends(resolve_caller_context)]
