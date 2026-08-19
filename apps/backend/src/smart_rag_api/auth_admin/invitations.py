"""Create single-use team invitations through the privileged Auth Admin boundary."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import psycopg

from smart_rag_api.auth_admin.settings import PrivilegedAuthSettings


class InvitationServiceError(Exception):
    """Raised when invitation creation or delivery fails."""


@dataclass(frozen=True, slots=True)
class CreatedInvitation:
    """Invitation record returned once to the privileged caller.

    Attributes:
        invitation_id: Durable application invitation identifier.
        email: Normalized recipient address.
        role: Role assigned on acceptance.
        upload_enabled: Capability assigned on acceptance.
        expires_at: Absolute 24-hour expiry.
        raw_token: One-time secret used for mail delivery. Never returned over HTTP.
    """

    invitation_id: uuid.UUID
    email: str
    role: str
    upload_enabled: bool
    expires_at: datetime
    raw_token: str


def _token_hash(raw_token: str) -> str:
    """Return SHA-256 hex digest for invitation storage."""

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_invitation(
    settings: PrivilegedAuthSettings,
    *,
    postgres_url: str,
    email: str,
    role: str,
    invited_by: uuid.UUID,
    upload_enabled: bool = False,
) -> CreatedInvitation:
    """Create and deliver a domain-authorized 24-hour invitation.

    Args:
        settings: Privileged Auth Admin settings with service-role secret.
        postgres_url: Postgres URL for durable invitation rows (service path).
        email: Lowercase invitee email.
        role: Target ``app.user_role`` text.
        invited_by: Owner/admin user creating the invite.
        upload_enabled: Whether upload capability is granted on accept.

    Returns:
        Created invitation including the one-time raw token.

    Raises:
        InvitationServiceError: On authorization, domain, role, persistence, or
            provider delivery failure.

    Side Effects:
        Persists and audits the application invitation, then asks Supabase Auth to
        deliver mail. Provider failure revokes the application token.

    Security:
        Actor role and allowed domains are always loaded from authoritative rows;
        callers cannot provide either policy input.
    """

    normalized_email = email.strip().lower()
    if (
        not normalized_email
        or normalized_email.count("@") != 1
        or normalized_email.startswith("@")
        or normalized_email.endswith("@")
    ):
        raise InvitationServiceError("invalid invitation email")

    domain = normalized_email.split("@", maxsplit=1)[1]
    if role not in {"owner", "admin", "member", "viewer"}:
        raise InvitationServiceError("invalid invitation role")
    if role == "viewer" and upload_enabled:
        raise InvitationServiceError("viewer invitations cannot grant upload")

    raw_token = secrets.token_urlsafe(32)
    digest = _token_hash(raw_token)
    expires_at = datetime.now(tz=UTC) + timedelta(hours=24)
    invitation_id = uuid.uuid4()

    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT role::text
                FROM app.profiles
                WHERE user_id = %s
                  AND disabled_at IS NULL
                FOR SHARE
                """,
                (invited_by,),
            )
            actor_row = cursor.fetchone()
            if actor_row is None or str(actor_row[0]) not in {"owner", "admin"}:
                raise InvitationServiceError("invitation actor authorization rejected")
            actor_role = str(actor_row[0])
            if role == "owner" and actor_role != "owner":
                raise InvitationServiceError("only owner may invite owner")

            cursor.execute(
                """
                SELECT 1
                FROM app.allowed_email_domains
                WHERE domain = %s
                """,
                (domain,),
            )
            if cursor.fetchone() is None:
                raise InvitationServiceError("email domain not allowed")

            cursor.execute(
                """
                INSERT INTO app.team_invitations (
                  id,
                  email,
                  invited_by,
                  role,
                  token_hash,
                  expires_at,
                  upload_enabled
                )
                VALUES (%s, %s, %s, %s::app.user_role, %s, %s, %s)
                """,
                (
                    invitation_id,
                    normalized_email,
                    invited_by,
                    role,
                    digest,
                    expires_at,
                    upload_enabled,
                ),
            )
            cursor.execute(
                """
                SELECT app.append_audit_event(
                  'invitation.created',
                  %s,
                  %s::app.user_role,
                  'team_invitation',
                  %s,
                  app.current_authorization_version(),
                  jsonb_build_object(
                    'domain', %s::text,
                    'role', %s::text,
                    'upload_enabled', %s::boolean
                  )
                )
                """,
                (
                    invited_by,
                    actor_role,
                    invitation_id,
                    domain,
                    role,
                    upload_enabled,
                ),
            )
        connection.commit()

    try:
        send_provider_invite_email(
            settings,
            email=normalized_email,
            raw_token=raw_token,
        )
    except InvitationServiceError:
        _revoke_failed_invitation(
            postgres_url,
            invitation_id=invitation_id,
            actor_user_id=invited_by,
            actor_role=actor_role,
        )
        raise

    return CreatedInvitation(
        invitation_id=invitation_id,
        email=normalized_email,
        role=role,
        upload_enabled=upload_enabled,
        expires_at=expires_at,
        raw_token=raw_token,
    )


def _revoke_failed_invitation(
    postgres_url: str,
    *,
    invitation_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    actor_role: str,
) -> None:
    """Revoke and audit an application token after provider delivery failure.

    Args:
        postgres_url: Isolated privileged PostgreSQL URL.
        invitation_id: Invitation whose token must become unusable.
        actor_user_id: Original invitation actor.
        actor_role: Authoritative actor role captured during creation.

    Raises:
        InvitationServiceError: If compensation cannot be persisted.

    Side Effects:
        Sets ``revoked_at`` and appends a purpose-limited failure audit event.
    """

    try:
        with psycopg.connect(postgres_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE app.team_invitations
                    SET revoked_at = timezone('utc', now())
                    WHERE id = %s
                      AND accepted_at IS NULL
                      AND revoked_at IS NULL
                    """,
                    (invitation_id,),
                )
                cursor.execute(
                    """
                    SELECT app.append_audit_event(
                      'invitation.delivery_failed',
                      %s,
                      %s::app.user_role,
                      'team_invitation',
                      %s,
                      app.current_authorization_version(),
                      jsonb_build_object('token_revoked', true)
                    )
                    """,
                    (actor_user_id, actor_role, invitation_id),
                )
            connection.commit()
    except psycopg.Error as exc:
        raise InvitationServiceError(
            "failed invitation delivery compensation could not be persisted"
        ) from exc


def send_provider_invite_email(
    settings: PrivilegedAuthSettings,
    *,
    email: str,
    raw_token: str,
) -> None:
    """Send an Auth Admin invite email; local development uses Inbucket SMTP.

    Args:
        settings: Privileged settings containing Auth Admin secret.
        email: Recipient email address.
        raw_token: One-time token embedded in the invite link.

    Raises:
        InvitationServiceError: When the Auth Admin REST call fails.
    """

    base = str(settings.supabase_url).rstrip("/")
    invite_url = f"{base}/auth/v1/verify?token={raw_token}&type=invite"
    admin_secret = settings.supabase_auth_admin_secret.get_secret_value()

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{base}/auth/v1/invite",
                headers={
                    "Authorization": f"Bearer {admin_secret}",
                    "apikey": admin_secret,
                },
                json={
                    "email": email,
                    "data": {"invite_url": invite_url},
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise InvitationServiceError("auth admin invite call failed") from exc
