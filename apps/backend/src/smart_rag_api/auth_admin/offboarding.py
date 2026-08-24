"""Immediate authorization and session effects for user offboarding."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import httpx
import psycopg

from smart_rag_api.auth_admin.settings import PrivilegedAuthSettings


class OffboardingError(Exception):
    """Raised when offboarding authorization or provider revocation fails."""


@dataclass(frozen=True, slots=True)
class CompletedOffboarding:
    """Completed Phase 2 offboarding security effects.

    Attributes:
        request_id: Durable offboarding workflow identifier.
        subject_user_id: Disabled user.
        completed_at: Database completion time in UTC.
    """

    request_id: uuid.UUID
    subject_user_id: uuid.UUID
    completed_at: datetime


def _require_offboarding_actor(
    cursor: psycopg.Cursor[tuple[object, ...]],
    *,
    actor_user_id: uuid.UUID,
    asserted_role: str,
    assurance_level: str,
) -> str:
    """Return an authoritative privileged actor role.

    Args:
        cursor: Cursor in the offboarding transaction.
        actor_user_id: Verified caller subject.
        asserted_role: Role from the verified caller context.
        assurance_level: Verified Supabase JWT ``aal`` claim.

    Returns:
        Authoritative owner/admin role.

    Raises:
        OffboardingError: If the actor is disabled, unprivileged, or stale/forged.
            ``assurance_level`` is retained and ignored.
    """

    _ = assurance_level
    cursor.execute(
        """
        SELECT role::text
        FROM app.profiles
        WHERE user_id = %s
          AND disabled_at IS NULL
        FOR SHARE
        """,
        (actor_user_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise OffboardingError("offboarding actor is not active")
    role = str(row[0])
    if role not in {"owner", "admin"} or role != asserted_role:
        raise OffboardingError("offboarding actor authorization rejected")
    return role


def revoke_provider_sessions(
    settings: PrivilegedAuthSettings,
    subject_user_id: uuid.UUID,
) -> None:
    """Revoke all provider sessions for one offboarded user.

    Args:
        settings: Isolated Auth Admin settings.
        subject_user_id: User whose provider sessions must be revoked.

    Raises:
        OffboardingError: If the bounded Auth Admin call fails.

    Side Effects:
        Calls GoTrue global logout with a ten-second timeout. The secret and
        provider response body are never logged.
    """

    base = str(settings.supabase_url).rstrip("/")
    admin_secret = settings.supabase_auth_admin_secret.get_secret_value()
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{base}/auth/v1/admin/users/{subject_user_id}/logout",
                headers={
                    "Authorization": f"Bearer {admin_secret}",
                    "apikey": admin_secret,
                },
                json={"scope": "global"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OffboardingError(
            "offboarding provider session revocation failed"
        ) from exc


def apply_offboarding_security(
    settings: PrivilegedAuthSettings,
    postgres_url: str,
    *,
    subject_user_id: uuid.UUID,
    requested_by: uuid.UUID,
    actor_role: str,
    actor_assurance_level: str,
) -> CompletedOffboarding:
    """Apply the Phase 2 security subset of user offboarding.

    Args:
        settings: Isolated Auth Admin settings.
        postgres_url: Isolated privileged PostgreSQL URL.
        subject_user_id: User to disable.
        requested_by: Verified owner/admin actor.
        actor_role: Role from the verified caller context.
        actor_assurance_level: Verified actor JWT ``aal`` claim.

    Returns:
        Durable completed offboarding record.

    Raises:
        OffboardingError: If the actor/subject is invalid, the subject is the last
            active owner, or provider session revocation fails.

    Side Effects:
        Creates an offboarding record, globally logs out the subject, disables the
        profile, removes upload and MFA capability state, records profile-wide
        session revocation, bumps authorization version, and appends an audit
        event. Purge/export execution remains owned by a later phase.

    Idempotency:
        Repeated calls after the profile is disabled fail without creating another
        request.
    """

    request_id = uuid.uuid4()
    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            authoritative_role = _require_offboarding_actor(
                cursor,
                actor_user_id=requested_by,
                asserted_role=actor_role,
                assurance_level=actor_assurance_level,
            )
            cursor.execute(
                """
                SELECT role::text, disabled_at
                FROM app.profiles
                WHERE user_id = %s
                FOR UPDATE
                """,
                (subject_user_id,),
            )
            subject_row = cursor.fetchone()
            if subject_row is None or subject_row[1] is not None:
                raise OffboardingError("offboarding subject is not active")
            subject_role = str(subject_row[0])
            if subject_role == "owner":
                cursor.execute(
                    """
                    SELECT count(*)::integer
                    FROM app.profiles
                    WHERE role = 'owner'::app.user_role
                      AND disabled_at IS NULL
                      AND user_id <> %s
                    """,
                    (subject_user_id,),
                )
                owner_count_row = cursor.fetchone()
                if owner_count_row is None or int(owner_count_row[0]) == 0:
                    raise OffboardingError("last active owner cannot be offboarded")

            cursor.execute(
                """
                INSERT INTO app.offboarding_requests (
                  id,
                  subject_user_id,
                  requested_by,
                  status
                )
                VALUES (%s, %s, %s, 'in_progress')
                """,
                (request_id, subject_user_id, requested_by),
            )
            revoke_provider_sessions(settings, subject_user_id)
            cursor.execute(
                """
                UPDATE app.profiles
                SET
                  disabled_at = timezone('utc', now()),
                  upload_enabled = false,
                  mfa_enrolled = false
                WHERE user_id = %s
                """,
                (subject_user_id,),
            )
            cursor.execute(
                "SELECT app.revoke_session(%s, %s)",
                (f"offboarding:{request_id}", subject_user_id),
            )
            cursor.execute(
                """
                UPDATE app.offboarding_requests
                SET
                  status = 'completed',
                  completed_at = timezone('utc', now())
                WHERE id = %s
                RETURNING completed_at
                """,
                (request_id,),
            )
            completed_row = cursor.fetchone()
            if completed_row is None or not isinstance(completed_row[0], datetime):
                raise OffboardingError("offboarding completion persistence failed")
            completed_at = completed_row[0]
            cursor.execute(
                """
                SELECT app.append_audit_event(
                  'user.offboarded',
                  %s,
                  %s::app.user_role,
                  'user',
                  %s,
                  app.current_authorization_version(),
                  jsonb_build_object(
                    'request_id', %s::text,
                    'sessions_revoked', true,
                    'upload_enabled', false,
                    'purge_deferred', true
                  )
                )
                """,
                (
                    requested_by,
                    authoritative_role,
                    subject_user_id,
                    request_id,
                ),
            )
        connection.commit()

    return CompletedOffboarding(
        request_id=request_id,
        subject_user_id=subject_user_id,
        completed_at=completed_at,
    )
