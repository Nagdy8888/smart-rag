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
    """Invitation record returned once to the privileged caller."""

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
    allowed_domains: tuple[str, ...] = (),
) -> CreatedInvitation:
    """Create a 24-hour single-use invitation and optionally send provider email.

    Args:
        settings: Privileged Auth Admin settings with service-role secret.
        postgres_url: Postgres URL for durable invitation rows (service path).
        email: Lowercase invitee email.
        role: Target ``app.user_role`` text.
        invited_by: Owner/admin user creating the invite.
        upload_enabled: Whether upload capability is granted on accept.
        allowed_domains: When non-empty, reject emails outside the allow-list.

    Returns:
        Created invitation including the one-time raw token.

    Raises:
        InvitationServiceError: On domain policy violation or persistence errors.
    """

    normalized_email = email.strip().lower()
    if not normalized_email or "@" not in normalized_email:
        raise InvitationServiceError("invalid invitation email")

    domain = normalized_email.split("@", maxsplit=1)[1]
    if allowed_domains and domain not in allowed_domains:
        raise InvitationServiceError("email domain not allowed")

    raw_token = secrets.token_urlsafe(32)
    digest = _token_hash(raw_token)
    expires_at = datetime.now(tz=UTC) + timedelta(hours=24)
    invitation_id = uuid.uuid4()

    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
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
        connection.commit()

    _send_provider_invite_email(
        settings,
        email=normalized_email,
        raw_token=raw_token,
    )

    return CreatedInvitation(
        invitation_id=invitation_id,
        email=normalized_email,
        role=role,
        upload_enabled=upload_enabled,
        expires_at=expires_at,
        raw_token=raw_token,
    )


def _send_provider_invite_email(
    settings: PrivilegedAuthSettings,
    *,
    email: str,
    raw_token: str,
) -> None:
    """Best-effort Auth Admin invite email; local dev uses Inbucket SMTP.

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
                    "data": {"invitation_token": raw_token, "invite_url": invite_url},
                },
            )
            if response.status_code >= 400 and response.status_code != 422:
                raise InvitationServiceError("auth admin invite call failed")
    except httpx.HTTPError as exc:
        raise InvitationServiceError("auth admin invite transport failed") from exc
