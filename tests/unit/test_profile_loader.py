"""Unit tests for MFA-free caller context construction (P08-11)."""

from __future__ import annotations

from smart_rag_api.services.profile_loader import ProfileSnapshot, build_caller_context
from smart_rag_core.security.identity import UserRole

_OWNER_ID = "11111111-1111-1111-1111-111111111111"
_MEMBER_ID = "22222222-2222-2222-2222-222222222222"


def _snapshot(
    *,
    user_id: str,
    role: UserRole,
    upload_enabled: bool,
    mfa_enrolled: bool,
) -> ProfileSnapshot:
    """Build a profile snapshot for caller-context tests.

    Args:
        user_id: Subject UUID string.
        role: Authoritative role.
        upload_enabled: Upload capability flag.
        mfa_enrolled: Dormant compatibility flag.

    Returns:
        Frozen profile snapshot.
    """

    return ProfileSnapshot(
        user_id=user_id,
        role=role,
        authorization_version=1,
        disabled=False,
        upload_enabled=upload_enabled,
        mfa_enrolled=mfa_enrolled,
        session_revoked_at=None,
    )


def test_owner_at_aal1_without_enrolled_mfa_is_authorized() -> None:
    """Owner/admin authorization ignores AAL and the dormant MFA flag."""

    context = build_caller_context(
        _snapshot(
            user_id=_OWNER_ID,
            role=UserRole.OWNER,
            upload_enabled=False,
            mfa_enrolled=False,
        ),
        session_id="session-owner",
        assurance_level="aal1",
        authentication_methods=("password",),
    )
    assert context.role is UserRole.OWNER
    assert context.mfa_enrolled is False
    assert context.upload_enabled is False


def test_upload_member_context_never_reads_mfa_enrolled() -> None:
    """Upload-capable members are authorized without treating MFA as a gate."""

    context = build_caller_context(
        _snapshot(
            user_id=_MEMBER_ID,
            role=UserRole.MEMBER,
            upload_enabled=True,
            mfa_enrolled=True,
        ),
        session_id=None,
        assurance_level="aal1",
        authentication_methods=(),
    )
    assert context.upload_enabled is True
    assert context.mfa_enrolled is False


def test_backend_identity_modules_do_not_emit_mfa_required() -> None:
    """Live identity and privileged-admin modules must not emit MFA required."""

    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    scanned = [
        root / "apps/backend/src/smart_rag_api/dependencies/identity.py",
        root / "apps/backend/src/smart_rag_api/services/profile_loader.py",
        root / "apps/backend/src/smart_rag_api/auth_admin/offboarding.py",
        root / "apps/backend/src/smart_rag_api/auth_admin/mfa_recovery.py",
        root / "apps/backend/src/smart_rag_api/routers/auth_team.py",
    ]
    haystack = "\n".join(path.read_text(encoding="utf-8") for path in scanned)
    assert "MFA required" not in haystack
    assert "must use an AAL2 session" not in haystack
    assert 'assurance_level != "aal2"' not in haystack
