"""Lost-factor MFA recovery through the privileged Auth Admin boundary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

import httpx
import psycopg

from smart_rag_api.auth_admin.settings import PrivilegedAuthSettings


class MfaRecoveryError(Exception):
    """Raised when MFA recovery violates policy or a privileged call fails."""


@dataclass(frozen=True, slots=True)
class MfaRecoveryRequest:
    """Audited MFA recovery workflow state.

    Attributes:
        request_id: Durable workflow identifier.
        subject_user_id: User whose lost factor is being reset.
        initiated_by: Distinct owner/admin who verified the subject.
        status: Persisted workflow status.
        created_at: Database creation time in UTC.
    """

    request_id: uuid.UUID
    subject_user_id: uuid.UUID
    initiated_by: uuid.UUID
    status: str
    created_at: datetime


def _require_active_recovery_actor(
    cursor: psycopg.Cursor[tuple[object, ...]],
    *,
    actor_id: uuid.UUID,
    asserted_role: str,
    assurance_level: str,
) -> str:
    """Validate a recovery actor against the authoritative profile.

    Args:
        cursor: Cursor in the recovery transaction.
        actor_id: Verified actor subject.
        asserted_role: Role from the verified caller context.
        assurance_level: Verified Supabase JWT ``aal`` claim.

    Returns:
        The authoritative owner/admin role.

    Raises:
        MfaRecoveryError: If the actor is disabled, unprivileged, stale/forged,
            or not authenticated at AAL2.
    """

    if assurance_level != "aal2":
        raise MfaRecoveryError("MFA recovery actor must use an AAL2 session")

    cursor.execute(
        """
        SELECT role::text
        FROM app.profiles
        WHERE user_id = %s
          AND disabled_at IS NULL
        FOR SHARE
        """,
        (actor_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise MfaRecoveryError("MFA recovery actor is not active")

    role = str(row[0])
    if role not in {"owner", "admin"} or role != asserted_role:
        raise MfaRecoveryError("MFA recovery actor authorization rejected")
    return role


def _validate_verification_metadata(method: str, reference: str) -> tuple[str, str]:
    """Normalize bounded, non-secret identity-verification metadata.

    Args:
        method: Out-of-band verification method label.
        reference: External case or ticket identifier.

    Returns:
        Trimmed method and reference.

    Raises:
        MfaRecoveryError: If either value is unbounded or contains control lines.
    """

    normalized_method = method.strip()
    normalized_reference = reference.strip()
    if not 3 <= len(normalized_method) <= 64:
        raise MfaRecoveryError("verification method must contain 3-64 characters")
    if not 3 <= len(normalized_reference) <= 128:
        raise MfaRecoveryError("verification reference must contain 3-128 characters")
    if any(
        marker in normalized_method or marker in normalized_reference
        for marker in ("\r", "\n", "\0")
    ):
        raise MfaRecoveryError("verification metadata contains a control character")
    return normalized_method, normalized_reference


def initiate_mfa_recovery(
    postgres_url: str,
    *,
    subject_user_id: uuid.UUID,
    initiated_by: uuid.UUID,
    actor_role: str,
    actor_assurance_level: str,
    verification_method: str,
    verification_reference: str,
) -> MfaRecoveryRequest:
    """Record verified recovery initiation and immediately suspend capabilities.

    Args:
        postgres_url: Isolated privileged PostgreSQL URL.
        subject_user_id: User who lost MFA access.
        initiated_by: Distinct owner/admin who verified the subject.
        actor_role: Role from the verified caller context.
        actor_assurance_level: Verified actor JWT ``aal`` claim.
        verification_method: Non-secret out-of-band method label.
        verification_reference: Non-secret external case/ticket identifier.

    Returns:
        Persisted recovery request in ``initiated`` status.

    Raises:
        MfaRecoveryError: If the actor or subject is invalid, self-recovery is
            attempted, or verification metadata violates policy.

    Side Effects:
        Persists an append-only verification reference, disables upload/MFA state,
        invalidates existing bearer sessions, bumps authorization version, and
        appends an audit event in one transaction.

    Security:
        The verification reference must identify an external record and must never
        contain identity evidence, transcripts, codes, or provider secrets.
    """

    method, reference = _validate_verification_metadata(
        verification_method,
        verification_reference,
    )
    if subject_user_id == initiated_by:
        raise MfaRecoveryError("MFA recovery requires a distinct verified actor")

    request_id = uuid.uuid4()
    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            authoritative_role = _require_active_recovery_actor(
                cursor,
                actor_id=initiated_by,
                asserted_role=actor_role,
                assurance_level=actor_assurance_level,
            )
            cursor.execute(
                """
                SELECT 1
                FROM app.profiles
                WHERE user_id = %s
                  AND disabled_at IS NULL
                FOR UPDATE
                """,
                (subject_user_id,),
            )
            if cursor.fetchone() is None:
                raise MfaRecoveryError("MFA recovery subject is not active")

            cursor.execute(
                """
                INSERT INTO app.mfa_recovery_requests (
                  id,
                  subject_user_id,
                  initiated_by,
                  status
                )
                VALUES (%s, %s, %s, 'initiated')
                RETURNING created_at
                """,
                (request_id, subject_user_id, initiated_by),
            )
            created_row = cursor.fetchone()
            if created_row is None or not isinstance(created_row[0], datetime):
                raise MfaRecoveryError("MFA recovery request persistence failed")
            created_at = created_row[0]

            cursor.execute(
                """
                INSERT INTO app.mfa_recovery_verifications (
                  recovery_request_id,
                  subject_user_id,
                  verified_by,
                  verification_method,
                  verification_reference
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    request_id,
                    subject_user_id,
                    initiated_by,
                    method,
                    reference,
                ),
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
                "SELECT app.revoke_session(%s, %s)",
                (f"mfa-recovery:{request_id}", subject_user_id),
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
                  jsonb_build_object(
                    'request_id', %s::text,
                    'verification_method', %s::text,
                    'capabilities_suspended', true
                  )
                )
                """,
                (
                    initiated_by,
                    authoritative_role,
                    subject_user_id,
                    request_id,
                    method,
                ),
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
    actor_assurance_level: str,
) -> None:
    """Reset factors and sessions before marking recovery complete.

    Args:
        settings: Isolated Auth Admin endpoint and secret settings.
        postgres_url: Isolated privileged PostgreSQL URL.
        request_id: Existing initiated recovery request identifier.
        completed_by: Distinct owner/admin completing the workflow.
        actor_role: Role from the verified caller context.
        actor_assurance_level: Verified actor JWT ``aal`` claim.

    Raises:
        MfaRecoveryError: If authorization, workflow state, factor inventory, or
            a privileged provider call fails.

    Side Effects:
        Deletes every provider MFA factor, revokes every provider session, records
        a profile-wide revocation time, preserves upload downgrade, bumps the
        authorization snapshot as applicable, and appends an audit event.

    Idempotency:
        A previously completed request returns without repeating provider calls.
    """

    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            authoritative_role = _require_active_recovery_actor(
                cursor,
                actor_id=completed_by,
                asserted_role=actor_role,
                assurance_level=actor_assurance_level,
            )
            cursor.execute(
                """
                SELECT request.subject_user_id, request.status, verification.expires_at
                FROM app.mfa_recovery_requests AS request
                LEFT JOIN app.mfa_recovery_verifications AS verification
                  ON verification.recovery_request_id = request.id
                WHERE request.id = %s
                FOR UPDATE OF request
                """,
                (request_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise MfaRecoveryError("MFA recovery request not found")
            subject_user_id = uuid.UUID(str(row[0]))
            status = str(row[1])
            expires_at = row[2]
            if status == "completed":
                return
            if status != "initiated":
                raise MfaRecoveryError("MFA recovery request not active")
            if not isinstance(expires_at, datetime):
                raise MfaRecoveryError("MFA recovery request expiry is invalid")
            if datetime.now(tz=expires_at.tzinfo) >= expires_at:
                cursor.execute(
                    """
                    UPDATE app.mfa_recovery_requests
                    SET status = 'cancelled'
                    WHERE id = %s
                    """,
                    (request_id,),
                )
                connection.commit()
                raise MfaRecoveryError("MFA recovery request expired")
            if completed_by == subject_user_id:
                raise MfaRecoveryError(
                    "MFA recovery requires a distinct completing actor"
                )

            cursor.execute(
                """
                SELECT 1
                FROM app.profiles
                WHERE user_id = %s
                  AND disabled_at IS NULL
                FOR UPDATE
                """,
                (subject_user_id,),
            )
            if cursor.fetchone() is None:
                raise MfaRecoveryError("MFA recovery subject is not active")
            cursor.execute(
                """
                SELECT 1
                FROM app.mfa_recovery_verifications
                WHERE recovery_request_id = %s
                  AND subject_user_id = %s
                """,
                (request_id, subject_user_id),
            )
            if cursor.fetchone() is None:
                raise MfaRecoveryError("MFA recovery verification evidence is missing")

            removed_factor_count = reset_mfa_and_sessions_via_auth_admin(
                settings,
                subject_user_id,
            )
            cursor.execute(
                """
                UPDATE app.profiles
                SET
                  mfa_enrolled = false,
                  upload_enabled = false
                WHERE user_id = %s
                """,
                (subject_user_id,),
            )
            cursor.execute(
                "SELECT app.revoke_session(%s, %s)",
                (f"mfa-recovery:{request_id}:completed", subject_user_id),
            )
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
                SELECT app.append_audit_event(
                  'mfa_recovery.completed',
                  %s,
                  %s::app.user_role,
                  'user',
                  %s,
                  app.current_authorization_version(),
                  jsonb_build_object(
                    'request_id', %s::text,
                    'removed_factor_count', %s::integer,
                    'sessions_revoked', true,
                    'upload_enabled', false
                  )
                )
                """,
                (
                    completed_by,
                    authoritative_role,
                    subject_user_id,
                    request_id,
                    removed_factor_count,
                ),
            )
        connection.commit()


def _factor_ids(payload: object) -> tuple[uuid.UUID, ...]:
    """Validate an Auth Admin MFA factor-list response.

    Args:
        payload: Untrusted JSON returned by GoTrue.

    Returns:
        All factor identifiers when at least one factor is verified.

    Raises:
        MfaRecoveryError: If the response is malformed or has no verified factor.
    """

    if not isinstance(payload, list):
        raise MfaRecoveryError("auth admin factor inventory is invalid")

    identifiers: list[uuid.UUID] = []
    has_verified_factor = False
    for raw_factor in cast(list[object], payload):
        if not isinstance(raw_factor, dict):
            raise MfaRecoveryError("auth admin factor inventory is invalid")
        factor = cast(dict[object, object], raw_factor)
        factor_id = factor.get("id")
        status = factor.get("status")
        if not isinstance(factor_id, str) or not isinstance(status, str):
            raise MfaRecoveryError("auth admin factor inventory is invalid")
        try:
            identifiers.append(uuid.UUID(factor_id))
        except ValueError as exc:
            raise MfaRecoveryError("auth admin factor identifier is invalid") from exc
        has_verified_factor = has_verified_factor or status == "verified"

    if not has_verified_factor:
        raise MfaRecoveryError("MFA recovery subject has no verified factor")
    return tuple(identifiers)


def reset_mfa_and_sessions_via_auth_admin(
    settings: PrivilegedAuthSettings,
    user_id: uuid.UUID,
) -> int:
    """Delete all MFA factors and revoke all sessions through Auth Admin.

    Args:
        settings: Privileged settings with the isolated Auth Admin secret.
        user_id: Recovery subject.

    Returns:
        Number of provider MFA factors removed.

    Raises:
        MfaRecoveryError: If factor inventory, deletion, or global logout fails.

    Side Effects:
        Calls the current GoTrue admin factor and global logout endpoints with a
        ten-second timeout. Secrets and provider response bodies are never logged.
    """

    base = str(settings.supabase_url).rstrip("/")
    admin_secret = settings.supabase_auth_admin_secret.get_secret_value()
    headers = {
        "Authorization": f"Bearer {admin_secret}",
        "apikey": admin_secret,
    }
    try:
        with httpx.Client(timeout=10.0, headers=headers) as client:
            factor_response = client.get(
                f"{base}/auth/v1/admin/users/{user_id}/factors"
            )
            factor_response.raise_for_status()
            try:
                factor_payload: object = factor_response.json()
            except ValueError as exc:
                raise MfaRecoveryError(
                    "auth admin factor inventory is invalid"
                ) from exc
            factor_ids = _factor_ids(factor_payload)

            for factor_id in factor_ids:
                delete_response = client.delete(
                    f"{base}/auth/v1/admin/users/{user_id}/factors/{factor_id}"
                )
                delete_response.raise_for_status()

            logout_response = client.post(
                f"{base}/auth/v1/admin/users/{user_id}/logout",
                json={"scope": "global"},
            )
            logout_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MfaRecoveryError("auth admin MFA reset failed") from exc
    return len(factor_ids)
