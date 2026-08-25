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

    Side Effects:
        Opens one short-lived ``app_api`` connection. Does not mint identity
        from JWT role claims.
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

    Side Effects:
        May open one short-lived ``app_api`` connection to read
        ``app.revoked_sessions``.
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
    """Map a profile snapshot into ``CallerContext`` without MFA authorization.

    ``assurance_level`` and ``authentication_methods`` remain in the signature
    for call compatibility. They are ignored and never authorize.

    Args:
        snapshot: Authoritative profile row.
        session_id: Verified JWT session identifier.
        assurance_level: Deprecated JWT ``aal`` claim; ignored.
        authentication_methods: Deprecated JWT ``amr`` methods; ignored.

    Returns:
        Frozen caller context for RPC binding. ``mfa_enrolled`` is always
        ``False`` so no caller can authorize from the dormant profile flag.
    """

    _ = (assurance_level, authentication_methods)
    return CallerContext(
        user_id=snapshot.user_id,
        role=snapshot.role,
        authorization_version=snapshot.authorization_version,
        session_id=session_id,
        disabled=snapshot.disabled,
        upload_enabled=snapshot.upload_enabled,
        mfa_enrolled=False,
    )
