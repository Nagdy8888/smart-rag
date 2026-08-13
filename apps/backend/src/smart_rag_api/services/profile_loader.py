"""Load authoritative profile and company settings for caller resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
from smart_rag_core.security.identity import CallerContext, UserRole


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    """Authoritative membership row plus company authorization snapshot."""

    user_id: str
    role: UserRole
    authorization_version: int
    disabled: bool
    upload_enabled: bool
    mfa_enrolled: bool
    session_revoked_at: datetime | None


def load_profile_snapshot(
    postgres_url: str,
    *,
    user_id: str,
) -> ProfileSnapshot | None:
    """Read profile and company authorization_version as ``app_api``.

    Args:
        postgres_url: Postgres connection URL.
        user_id: Verified JWT subject UUID string.

    Returns:
        Snapshot when a profile exists; otherwise ``None``.
    """

    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_api")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                  p.role::text,
                  p.upload_enabled,
                  p.mfa_enrolled,
                  p.disabled_at,
                  p.session_revoked_at,
                  cs.authorization_version
                FROM app.profiles AS p
                CROSS JOIN app.company_settings AS cs
                WHERE p.user_id = %s::uuid
                  AND cs.id = '00000000-0000-0000-0000-000000000001'::uuid
                """,
                (user_id,),
            )
            row = cursor.fetchone()

    if row is None:
        return None

    disabled_at = row[3]
    return ProfileSnapshot(
        user_id=user_id,
        role=UserRole(row[0]),
        authorization_version=int(row[5]),
        disabled=disabled_at is not None,
        upload_enabled=bool(row[1]),
        mfa_enrolled=bool(row[2]),
        session_revoked_at=row[4],
    )


def is_session_revoked(
    postgres_url: str,
    *,
    session_id: str | None,
    issued_at: int | None,
    session_revoked_at: datetime | None,
) -> bool:
    """Return whether the bearer session must be rejected.

    Args:
        postgres_url: Postgres connection URL.
        session_id: JWT ``session_id`` claim when present.
        issued_at: JWT ``iat`` claim epoch seconds when present.
        session_revoked_at: Profile-wide revocation timestamp.

    Returns:
        ``True`` when the session or token predates revocation.
    """

    if session_revoked_at is not None and issued_at is not None:
        revoked_epoch = int(session_revoked_at.replace(tzinfo=UTC).timestamp())
        if issued_at <= revoked_epoch:
            return True

    if session_id is None:
        return False

    with psycopg.connect(postgres_url) as connection:
        connection.execute("SET ROLE app_api")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM app.revoked_sessions
                WHERE session_id = %s
                """,
                (session_id,),
            )
            return cursor.fetchone() is not None


def build_caller_context(
    snapshot: ProfileSnapshot,
    *,
    session_id: str | None,
    assurance_level: str | None,
    authentication_methods: tuple[str, ...],
) -> CallerContext:
    """Map a profile snapshot and JWT MFA signals into ``CallerContext``.

    Args:
        snapshot: Authoritative profile row.
        session_id: Verified JWT session identifier.
        assurance_level: JWT ``aal`` claim when present.
        authentication_methods: JWT ``amr`` methods.

    Returns:
        Frozen caller context for RPC binding.

    Raises:
        ValueError: When MFA is required but not satisfied.
    """

    requires_mfa = (
        snapshot.role in {UserRole.OWNER, UserRole.ADMIN} or snapshot.upload_enabled
    )
    mfa_satisfied = snapshot.mfa_enrolled and (
        assurance_level in {"aal2", "aal3"}
        or "mfa" in authentication_methods
        or "totp" in authentication_methods
    )
    if requires_mfa and not mfa_satisfied:
        raise ValueError("mfa required")

    return CallerContext(
        user_id=snapshot.user_id,
        role=snapshot.role,
        authorization_version=snapshot.authorization_version,
        session_id=session_id,
        disabled=snapshot.disabled,
        upload_enabled=snapshot.upload_enabled,
        mfa_enrolled=snapshot.mfa_enrolled,
    )
