"""FastAPI dependency for JWKS-verified caller identity (Packet 4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from smart_rag_core.security.identity import CallerContext
from smart_rag_core.security.jwks import JwksVerificationError, JwksVerifier
from smart_rag_core.settings import BackendSettings, Environment

from smart_rag_api.services.profile_loader import (
    build_caller_context,
    is_session_revoked,
    load_profile_snapshot,
)

_AUTHORIZATION_HEADER = "Authorization"
_TEST_USER_ID_HEADER = "X-Test-User-Id"
_TEST_ROLE_HEADER = "X-Test-Role"
_TEST_AUTHZ_VERSION_HEADER = "X-Test-Authorization-Version"


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Parse ``Authorization: Bearer`` value."""

    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _resolve_test_bypass(
    settings: BackendSettings,
    *,
    x_test_user_id: str | None,
    x_test_role: str | None,
    x_test_authorization_version: int | None,
) -> CallerContext | None:
    """Return a test-only caller context when explicitly gated."""

    if settings.app_env is not Environment.TEST:
        return None
    if (
        x_test_user_id is None
        or x_test_role is None
        or x_test_authorization_version is None
    ):
        return None
    return CallerContext.from_profile_row(
        user_id=x_test_user_id,
        role=x_test_role,
        authorization_version=x_test_authorization_version,
    )


def resolve_caller_context(
    request: Request,
    authorization: Annotated[str | None, Header(alias=_AUTHORIZATION_HEADER)] = None,
    x_test_user_id: Annotated[str | None, Header(alias=_TEST_USER_ID_HEADER)] = None,
    x_test_role: Annotated[str | None, Header(alias=_TEST_ROLE_HEADER)] = None,
    x_test_authorization_version: Annotated[
        int | None, Header(alias=_TEST_AUTHZ_VERSION_HEADER)
    ] = None,
) -> CallerContext:
    """Resolve typed caller context from JWKS and live profile state.

    Args:
        request: Active FastAPI request with startup-bound settings and JWKS.
        authorization: Bearer access token header.
        x_test_user_id: Test-only subject bypass when ``APP_ENV=test``.
        x_test_role: Test-only role bypass when ``APP_ENV=test``.
        x_test_authorization_version: Test-only authorization snapshot bypass.

    Returns:
        Frozen ``CallerContext`` for RPC argument binding.

    Raises:
        HTTPException: When auth fails verification, profile is missing/disabled,
            session is revoked, or MFA is required but absent.
    """

    settings: BackendSettings = request.app.state.settings
    bypass = _resolve_test_bypass(
        settings,
        x_test_user_id=x_test_user_id,
        x_test_role=x_test_role,
        x_test_authorization_version=x_test_authorization_version,
    )
    if bypass is not None:
        if not bypass.is_active():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Caller disabled",
            )
        return bypass

    token = _extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer access token",
        )

    verifier: JwksVerifier = request.app.state.jwks_verifier
    try:
        verified = verifier.verify_access_token(token)
    except JwksVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc

    db_url = settings.supabase_db_url
    if db_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity store unavailable",
        )

    snapshot = load_profile_snapshot(
        db_url.get_secret_value(),
        user_id=verified.subject,
    )
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Membership profile missing",
        )
    if snapshot.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Caller disabled",
        )

    if is_session_revoked(
        db_url.get_secret_value(),
        session_id=verified.session_id,
        issued_at=verified.issued_at,
        session_revoked_at=snapshot.session_revoked_at,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked",
        )

    try:
        return build_caller_context(
            snapshot,
            session_id=verified.session_id,
            assurance_level=verified.assurance_level,
            authentication_methods=verified.authentication_methods,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA required",
        ) from exc


CallerContextDep = Annotated[CallerContext, Depends(resolve_caller_context)]
