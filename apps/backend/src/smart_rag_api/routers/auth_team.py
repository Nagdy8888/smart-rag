"""Thin auth/team HTTP routes over factory-injected services."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.settings import Environment

from smart_rag_api.auth_admin.invitations import InvitationServiceError
from smart_rag_api.auth_admin.offboarding import OffboardingError
from smart_rag_api.dependencies.identity import CallerContextDep
from smart_rag_api.dependencies.services import enforce_rate_limit, get_postgres_url
from smart_rag_api.schemas.fastapi_security import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    CreateInvitationRequest,
    CreateInvitationResponse,
    CurrentUserResponse,
    OffboardResponse,
)
from smart_rag_api.services.auth_rate_limits import RateLimitKind
from smart_rag_api.services.auth_team import AuthTeamService
from smart_rag_api.services.http_errors import raise_admission_http

router = APIRouter(tags=["auth"])


def get_auth_team_service(
    postgres_url: Annotated[str, Depends(get_postgres_url)],
) -> AuthTeamService:
    """Factory for invitation and offboarding HTTP operations.

    Args:
        postgres_url: Injected DSN.

    Returns:
        Auth/team service.
    """

    return AuthTeamService(postgres_url)


@router.get("/me", response_model=CurrentUserResponse)
def current_user(caller: CallerContextDep) -> CurrentUserResponse:
    """Return the server-derived caller snapshot.

    Args:
        caller: Authenticated caller.

    Returns:
        Role and capability flags. ``mfa_enrolled`` is always false.
    """

    return CurrentUserResponse(
        user_id=UUID(caller.user_id),
        role=caller.role.value,
        authorization_version=caller.authorization_version,
        upload_enabled=caller.upload_enabled,
        mfa_enrolled=False,
    )


@router.post(
    "/admin/invitations",
    response_model=CreateInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation_route(
    request: Request,
    body: CreateInvitationRequest,
    caller: CallerContextDep,
    service: Annotated[AuthTeamService, Depends(get_auth_team_service)],
) -> JSONResponse:
    """Create a 24-hour invitation. Owner/admin only.

    Args:
        request: Active request.
        body: Invitee email, role, and upload flag.
        caller: Authenticated caller.
        service: Injected auth/team service.

    Returns:
        Invitation identifiers. The one-time token is delivered by mail only.
        ``APP_ENV=test`` also sets ``X-Test-Invitation-Token``.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"invitation-create:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=10,
    )
    try:
        created = service.create_invitation(
            caller,
            email=body.email,
            role=body.role,
            upload_enabled=body.upload_enabled,
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except InvitationServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invitation_rejected",
        ) from exc
    headers: dict[str, str] = {}
    settings = getattr(request.app.state, "settings", None)
    app_env = getattr(settings, "app_env", None)
    if app_env is Environment.TEST:
        headers["X-Test-Invitation-Token"] = created.raw_token
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=CreateInvitationResponse(
            invitation_id=created.invitation_id,
            email=created.email,
            role=created.role,
            upload_enabled=created.upload_enabled,
            expires_at=created.expires_at,
        ).model_dump(mode="json"),
        headers=headers,
    )


@router.post("/invitations/accept", response_model=AcceptInvitationResponse)
def accept_invitation_route(
    request: Request,
    body: AcceptInvitationRequest,
    caller: CallerContextDep,
    service: Annotated[AuthTeamService, Depends(get_auth_team_service)],
) -> AcceptInvitationResponse:
    """Accept a single-use invitation. Email comes from the verified token.

    Args:
        request: Active request with ``caller_email``.
        body: Raw invitation token.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Accepted invitation id.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"invitation-accept:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=5,
    )
    email = getattr(request.state, "caller_email", None)
    assurance = getattr(request.state, "assurance_level", "aal1")
    try:
        invitation_id = service.accept_invitation(
            caller,
            raw_token=body.token,
            email=email if isinstance(email, str) else "",
            assurance_level=assurance if isinstance(assurance, str) else "aal1",
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    return AcceptInvitationResponse(invitation_id=invitation_id)


@router.post(
    "/admin/users/{user_id}/offboard",
    response_model=OffboardResponse,
)
def offboard_user_route(
    request: Request,
    user_id: UUID,
    caller: CallerContextDep,
    service: Annotated[AuthTeamService, Depends(get_auth_team_service)],
) -> OffboardResponse:
    """Disable one subject and revoke sessions. Owner/admin only.

    Args:
        request: Active request with assurance level.
        user_id: Subject user id.
        caller: Authenticated caller.
        service: Injected service.

    Returns:
        Completed offboarding identifiers.
    """

    enforce_rate_limit(
        request,
        bucket_key=f"offboard:{caller.user_id}",
        kind=RateLimitKind.AUTH_ADJACENT,
        max_attempts=10,
    )
    assurance = getattr(request.state, "assurance_level", "aal1")
    try:
        completed = service.offboard(
            caller,
            subject_user_id=user_id,
            assurance_level=assurance if isinstance(assurance, str) else "aal1",
        )
    except QueryAdmissionError as exc:
        raise_admission_http(exc)
    except OffboardingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="offboarding_rejected",
        ) from exc
    return OffboardResponse(
        request_id=completed.request_id,
        subject_user_id=completed.subject_user_id,
        completed_at=completed.completed_at,
    )
