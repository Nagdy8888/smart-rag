"""Lost-factor MFA recovery through the privileged Auth Admin boundary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import psycopg

from smart_rag_api.auth_admin.settings import PrivilegedAuthSettings


class MfaRecoveryError(Exception):
    """Raised when MFA recovery violates policy or privileged calls fail."""


@dataclass(frozen=True, slots=True)
class MfaRecoveryRequest:
    """Audited MFA recovery workflow state."""

    request_id: uuid.UUID
    subject_user_id: uuid.UUID
    initiated_by: uuid.UUID
    status: str
    created_at: datetime


def initiate_mfa_recovery(
    postgres_url: str,
    *,
    subject_user_id: uuid.UUID,
    initiated_by: uuid.UUID,
    actor_role: str,
) -> MfaRecoveryRequest:
    """Record initiation, suspend capabilities, and block unsafe last-owner paths.

    Args:
        postgres_url: Postgres URL with permission to write recovery rows.
        subject_user_id: User who lost MFA access.
        initiated_by: Owner/admin actor starting recovery.
        actor_role: Role of the initiating actor.

    Returns:
        Persisted recovery request in ``initiated`` status.

    Raises:
        MfaRecoveryError: When last-owner self-recovery would remove the only
            admin path or persistence fails.
    """

    if actor_role not in {"owner", "admin"}:
        raise MfaRecoveryError("recovery requires owner or admin actor")

    if subject_user_id == initiated_by and actor_role == "owner":
        if _is_only_active_owner(postgres_url, subject_user_id):
            raise MfaRecoveryError(
                "last owner cannot initiate self recovery without another admin"
            )

    request_id = uuid.uuid4()
    created_at = datetime.now(tz=UTC)

    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.mfa_recovery_requests (
                  id,
                  subject_user_id,
                  initiated_by,
                  status
                )
                VALUES (%s, %s, %s, 'initiated')
                """,
                (request_id, subject_user_id, initiated_by),
            )
            cursor.execute(
                """
                UPDATE app.profiles
                SET
                  upload_enabled = false,
                  mfa_enrolled = false
                WHERE user_id = %s
                """,
                (subject_user_id,),
            )
            cursor.execute(
                """
                SELECT app.append_audit_event(
                  'mfa_recovery.initiated',
                  %s,
                  %s::app.user_role,
                  'user',
                  %s,
                  app.current_authorization_version(),
                  jsonb_build_object('subject_user_id', %s::text)
                )
                """,
                (initiated_by, actor_role, subject_user_id, subject_user_id),
            )
        connection.commit()

    return MfaRecoveryRequest(
        request_id=request_id,
        subject_user_id=subject_user_id,
        initiated_by=initiated_by,
        status="initiated",
        created_at=created_at,
    )


def complete_mfa_recovery(
    settings: PrivilegedAuthSettings,
    postgres_url: str,
    *,
    request_id: uuid.UUID,
    completed_by: uuid.UUID,
    actor_role: str,
) -> None:
    """Complete recovery: revoke sessions via Auth Admin and require re-enrollment.

    Args:
        settings: Privileged Auth Admin settings.
        postgres_url: Postgres URL for recovery state updates.
        request_id: Existing initiated recovery request identifier.
        completed_by: Owner/admin completing the workflow.
        actor_role: Completing actor role text.

    Raises:
        MfaRecoveryError: When the request is missing or privileged calls fail.
    """

    if actor_role not in {"owner", "admin"}:
        raise MfaRecoveryError("recovery completion requires owner or admin")

    subject_user_id: uuid.UUID | None = None
    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT subject_user_id, status
                FROM app.mfa_recovery_requests
                WHERE id = %s
                FOR UPDATE
                """,
                (request_id,),
            )
            row = cursor.fetchone()
            if row is None or row[1] != "initiated":
                raise MfaRecoveryError("recovery request not active")
            subject_user_id = row[0]

            cursor.execute(
                """
                UPDATE app.mfa_recovery_requests
                SET status = 'completed', completed_at = timezone('utc', now())
                WHERE id = %s
                """,
                (request_id,),
            )
            cursor.execute(
                """
                UPDATE app.profiles
                SET
                  mfa_enrolled = false,
                  upload_enabled = false,
                  session_revoked_at = timezone('utc', now())
                WHERE user_id = %s
                """,
                (subject_user_id,),
            )
            cursor.execute(
                """
                SELECT app.append_audit_event(
                  'mfa_recovery.completed',
                  %s,
                  %s::app.user_role,
                  'user',
                  %s,
                  app.current_authorization_version(),
                  jsonb_build_object('request_id', %s::text)
                )
                """,
                (completed_by, actor_role, subject_user_id, request_id),
            )
        connection.commit()

    if subject_user_id is None:
        raise MfaRecoveryError("recovery subject missing after persistence")
    _revoke_all_sessions_via_auth_admin(settings, subject_user_id)


def _is_only_active_owner(postgres_url: str, user_id: uuid.UUID) -> bool:
    """Return whether ``user_id`` is the sole active owner profile."""

    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)::int
                FROM app.profiles
                WHERE role = 'owner'::app.user_role
                  AND disabled_at IS NULL
                  AND user_id <> %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
    if row is None:
        return True
    return int(row[0]) == 0


def _revoke_all_sessions_via_auth_admin(
    settings: PrivilegedAuthSettings,
    user_id: uuid.UUID,
) -> None:
    """Revoke all refresh sessions for one user through Auth Admin REST.

    Args:
        settings: Privileged settings with Auth Admin secret.
        user_id: Subject whose sessions must be revoked.

    Raises:
        MfaRecoveryError: When the Auth Admin logout call fails.
    """

    base = str(settings.supabase_url).rstrip("/")
    admin_secret = settings.supabase_auth_admin_secret.get_secret_value()
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{base}/auth/v1/admin/users/{user_id}/logout",
                headers={
                    "Authorization": f"Bearer {admin_secret}",
                    "apikey": admin_secret,
                },
                json={"scope": "global"},
            )
            if response.status_code >= 400:
                raise MfaRecoveryError("auth admin session revocation failed")
    except httpx.HTTPError as exc:
        raise MfaRecoveryError(
            "auth admin session revocation transport failed"
        ) from exc
