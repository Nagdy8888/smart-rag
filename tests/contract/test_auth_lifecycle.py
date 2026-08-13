"""Auth lifecycle, recovery, offboarding, and domain contracts."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta

import psycopg
import pytest
from smart_rag_api.auth_admin import invitations, mfa_recovery, offboarding
from smart_rag_api.auth_admin.settings import (
    PrivilegedAuthSettings,
    load_privileged_auth_settings,
)
from smart_rag_api.services.profile_loader import (
    is_session_revoked,
    load_profile_snapshot,
)

from tests.contract.integration_support import resolve_supabase_db_url, try_connect


@pytest.fixture
def postgres_url() -> Iterator[str]:
    """Yield the local Supabase URL or skip when the mandatory stack is absent."""

    url = resolve_supabase_db_url()
    connection = try_connect(url)
    if connection is None:
        pytest.skip(f"Local Supabase Postgres unreachable at {url}")
    connection.close()
    yield url


@pytest.fixture
def privileged_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> PrivilegedAuthSettings:
    """Build isolated Auth Admin settings without a checked-in credential."""

    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv(
        "SUPABASE_AUTH_ADMIN_SECRET",
        secrets.token_urlsafe(48),
    )
    return load_privileged_auth_settings()


def _insert_profile(
    postgres_url: str,
    *,
    user_id: uuid.UUID,
    email: str,
    role: str,
    upload_enabled: bool,
    mfa_enrolled: bool,
) -> None:
    """Insert one Auth user and authoritative profile for a contract test."""

    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth.users (
                  id, instance_id, aud, role, email, encrypted_password,
                  email_confirmed_at, created_at, updated_at
                )
                VALUES (
                  %s,
                  '00000000-0000-0000-0000-000000000000'::uuid,
                  'authenticated',
                  'authenticated',
                  %s,
                  crypt('test-password', gen_salt('bf')),
                  timezone('utc', now()),
                  timezone('utc', now()),
                  timezone('utc', now())
                )
                """,
                (user_id, email),
            )
            cursor.execute(
                """
                INSERT INTO app.profiles (
                  user_id,
                  role,
                  upload_enabled,
                  mfa_enrolled
                )
                VALUES (%s, %s::app.user_role, %s, %s)
                """,
                (user_id, role, upload_enabled, mfa_enrolled),
            )
        connection.commit()


def _authorization_version(postgres_url: str) -> int:
    """Return the current company authorization version."""

    with psycopg.connect(postgres_url) as connection:
        row = connection.execute(
            "SELECT app.current_authorization_version()"
        ).fetchone()
    assert row is not None
    return int(row[0])


def test_mfa_recovery_is_verified_audited_and_fail_closed(
    postgres_url: str,
    privileged_settings: PrivilegedAuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery records verification, suspends access, and resets provider state."""

    actor_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    _insert_profile(
        postgres_url,
        user_id=actor_id,
        email=f"recovery-admin-{actor_id}@example.com",
        role="admin",
        upload_enabled=False,
        mfa_enrolled=True,
    )
    _insert_profile(
        postgres_url,
        user_id=subject_id,
        email=f"recovery-subject-{subject_id}@example.com",
        role="member",
        upload_enabled=True,
        mfa_enrolled=True,
    )
    version_before = _authorization_version(postgres_url)

    request = mfa_recovery.initiate_mfa_recovery(
        postgres_url,
        subject_user_id=subject_id,
        initiated_by=actor_id,
        actor_role="admin",
        actor_assurance_level="aal2",
        verification_method="manager_video_call",
        verification_reference=f"case-{uuid.uuid4()}",
    )

    snapshot = load_profile_snapshot(
        postgres_url,
        user_id=str(subject_id),
    )
    assert snapshot is not None
    assert snapshot.upload_enabled is False
    assert snapshot.mfa_enrolled is False
    assert snapshot.session_revoked_at is not None
    assert snapshot.authorization_version > version_before
    issued_before_recovery = int(
        (snapshot.session_revoked_at - timedelta(seconds=1)).timestamp()
    )
    assert is_session_revoked(
        postgres_url,
        session_id=None,
        issued_at=issued_before_recovery,
        session_revoked_at=snapshot.session_revoked_at,
    )

    with psycopg.connect(postgres_url) as connection:
        verification = connection.execute(
            """
            SELECT
              verification_method,
              verification_reference,
              verified_by,
              expires_at > verified_at
            FROM app.mfa_recovery_verifications
            WHERE recovery_request_id = %s
            """,
            (request.request_id,),
        ).fetchone()
        audit_payload = connection.execute(
            """
            SELECT payload
            FROM app.audit_events
            WHERE event_type = 'mfa_recovery.initiated'
              AND target_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (subject_id,),
        ).fetchone()
    assert verification is not None
    assert verification[0] == "manager_video_call"
    assert verification[2] == actor_id
    assert verification[3] is True
    assert audit_payload is not None
    assert "verification_reference" not in audit_payload[0]

    reset_subjects: list[uuid.UUID] = []

    def reset_provider(
        settings: PrivilegedAuthSettings,
        user_id: uuid.UUID,
    ) -> int:
        """Record the isolated provider mutation used by this DB contract."""

        assert settings is privileged_settings
        reset_subjects.append(user_id)
        return 2

    monkeypatch.setattr(
        mfa_recovery,
        "reset_mfa_and_sessions_via_auth_admin",
        reset_provider,
    )
    mfa_recovery.complete_mfa_recovery(
        privileged_settings,
        postgres_url,
        request_id=request.request_id,
        completed_by=actor_id,
        actor_role="admin",
        actor_assurance_level="aal2",
    )
    mfa_recovery.complete_mfa_recovery(
        privileged_settings,
        postgres_url,
        request_id=request.request_id,
        completed_by=actor_id,
        actor_role="admin",
        actor_assurance_level="aal2",
    )
    assert reset_subjects == [subject_id]

    with psycopg.connect(postgres_url) as connection:
        completed = connection.execute(
            """
            SELECT status, completed_at
            FROM app.mfa_recovery_requests
            WHERE id = %s
            """,
            (request.request_id,),
        ).fetchone()
        completion_audit = connection.execute(
            """
            SELECT payload
            FROM app.audit_events
            WHERE event_type = 'mfa_recovery.completed'
              AND payload ->> 'request_id' = %s
            """,
            (str(request.request_id),),
        ).fetchone()
    assert completed is not None
    assert completed[0] == "completed"
    assert isinstance(completed[1], datetime)
    assert completion_audit is not None
    assert completion_audit[0]["removed_factor_count"] == 2
    assert completion_audit[0]["sessions_revoked"] is True

    with psycopg.connect(postgres_url) as connection:
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="append-only",
        ):
            connection.execute(
                """
                UPDATE app.mfa_recovery_verifications
                SET verification_reference = 'mutated-reference'
                WHERE recovery_request_id = %s
                """,
                (request.request_id,),
            )


def test_mfa_recovery_denies_self_recovery_and_provider_outage(
    postgres_url: str,
    privileged_settings: PrivilegedAuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct actors are mandatory and provider failure cannot mark completion."""

    actor_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    _insert_profile(
        postgres_url,
        user_id=actor_id,
        email=f"recovery-owner-{actor_id}@example.com",
        role="owner",
        upload_enabled=False,
        mfa_enrolled=True,
    )
    _insert_profile(
        postgres_url,
        user_id=subject_id,
        email=f"recovery-outage-{subject_id}@example.com",
        role="member",
        upload_enabled=True,
        mfa_enrolled=True,
    )

    with pytest.raises(
        mfa_recovery.MfaRecoveryError,
        match="distinct verified actor",
    ):
        mfa_recovery.initiate_mfa_recovery(
            postgres_url,
            subject_user_id=actor_id,
            initiated_by=actor_id,
            actor_role="owner",
            actor_assurance_level="aal2",
            verification_method="manager_video_call",
            verification_reference=f"case-{uuid.uuid4()}",
        )

    request = mfa_recovery.initiate_mfa_recovery(
        postgres_url,
        subject_user_id=subject_id,
        initiated_by=actor_id,
        actor_role="owner",
        actor_assurance_level="aal2",
        verification_method="manager_video_call",
        verification_reference=f"case-{uuid.uuid4()}",
    )

    def fail_provider(
        _settings: PrivilegedAuthSettings,
        _user_id: uuid.UUID,
    ) -> int:
        """Simulate a bounded Auth Admin outage."""

        raise mfa_recovery.MfaRecoveryError("provider unavailable")

    monkeypatch.setattr(
        mfa_recovery,
        "reset_mfa_and_sessions_via_auth_admin",
        fail_provider,
    )
    with pytest.raises(
        mfa_recovery.MfaRecoveryError,
        match="provider unavailable",
    ):
        mfa_recovery.complete_mfa_recovery(
            privileged_settings,
            postgres_url,
            request_id=request.request_id,
            completed_by=actor_id,
            actor_role="owner",
            actor_assurance_level="aal2",
        )

    with psycopg.connect(postgres_url) as connection:
        status = connection.execute(
            "SELECT status FROM app.mfa_recovery_requests WHERE id = %s",
            (request.request_id,),
        ).fetchone()
        completed_audit = connection.execute(
            """
            SELECT count(*)::integer
            FROM app.audit_events
            WHERE event_type = 'mfa_recovery.completed'
              AND payload ->> 'request_id' = %s
            """,
            (str(request.request_id),),
        ).fetchone()
    assert status == ("initiated",)
    assert completed_audit == (0,)


def test_offboarding_disables_revokes_and_bumps_authorization(
    postgres_url: str,
    privileged_settings: PrivilegedAuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offboarding applies immediate security effects before later-phase purge."""

    actor_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    _insert_profile(
        postgres_url,
        user_id=actor_id,
        email=f"offboarding-owner-{actor_id}@example.com",
        role="owner",
        upload_enabled=False,
        mfa_enrolled=True,
    )
    _insert_profile(
        postgres_url,
        user_id=subject_id,
        email=f"offboarding-subject-{subject_id}@example.com",
        role="member",
        upload_enabled=True,
        mfa_enrolled=True,
    )
    version_before = _authorization_version(postgres_url)
    revoked_subjects: list[uuid.UUID] = []

    def revoke_provider(
        settings: PrivilegedAuthSettings,
        user_id: uuid.UUID,
    ) -> None:
        """Record the isolated global logout used by this DB contract."""

        assert settings is privileged_settings
        revoked_subjects.append(user_id)

    monkeypatch.setattr(
        offboarding,
        "revoke_provider_sessions",
        revoke_provider,
    )
    completed = offboarding.apply_offboarding_security(
        privileged_settings,
        postgres_url,
        subject_user_id=subject_id,
        requested_by=actor_id,
        actor_role="owner",
        actor_assurance_level="aal2",
    )
    assert revoked_subjects == [subject_id]

    snapshot = load_profile_snapshot(
        postgres_url,
        user_id=str(subject_id),
    )
    assert snapshot is not None
    assert snapshot.disabled is True
    assert snapshot.upload_enabled is False
    assert snapshot.mfa_enrolled is False
    assert snapshot.authorization_version > version_before
    assert snapshot.session_revoked_at is not None
    issued_before_offboarding = int(
        (snapshot.session_revoked_at - timedelta(seconds=1)).timestamp()
    )
    assert is_session_revoked(
        postgres_url,
        session_id=None,
        issued_at=issued_before_offboarding,
        session_revoked_at=snapshot.session_revoked_at,
    )

    with psycopg.connect(postgres_url) as connection:
        request_row = connection.execute(
            """
            SELECT status, completed_at
            FROM app.offboarding_requests
            WHERE id = %s
            """,
            (completed.request_id,),
        ).fetchone()
        audit_row = connection.execute(
            """
            SELECT payload
            FROM app.audit_events
            WHERE event_type = 'user.offboarded'
              AND payload ->> 'request_id' = %s
            """,
            (str(completed.request_id),),
        ).fetchone()
    assert request_row is not None
    assert request_row[0] == "completed"
    assert isinstance(request_row[1], datetime)
    assert audit_row is not None
    assert audit_row[0]["purge_deferred"] is True

    with pytest.raises(offboarding.OffboardingError, match="not active"):
        offboarding.apply_offboarding_security(
            privileged_settings,
            postgres_url,
            subject_user_id=subject_id,
            requested_by=actor_id,
            actor_role="owner",
            actor_assurance_level="aal2",
        )


def test_invitation_domain_policy_is_authoritative_and_failure_revokes(
    postgres_url: str,
    privileged_settings: PrivilegedAuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller input cannot bypass allowed domains and failed mail revokes tokens."""

    actor_id = uuid.uuid4()
    allowed_domain = f"allowed-{uuid.uuid4().hex}.example"
    _insert_profile(
        postgres_url,
        user_id=actor_id,
        email=f"invitation-admin-{actor_id}@example.com",
        role="admin",
        upload_enabled=False,
        mfa_enrolled=True,
    )
    with psycopg.connect(postgres_url) as connection:
        connection.execute(
            "INSERT INTO app.allowed_email_domains (domain) VALUES (%s)",
            (allowed_domain,),
        )
        connection.commit()

    sent_recipients: list[str] = []

    def send_invite(
        _settings: PrivilegedAuthSettings,
        *,
        email: str,
        raw_token: str,
    ) -> None:
        """Record provider delivery without exposing the one-time token."""

        assert raw_token
        sent_recipients.append(email)

    monkeypatch.setattr(
        invitations,
        "send_provider_invite_email",
        send_invite,
    )
    with pytest.raises(
        invitations.InvitationServiceError,
        match="domain not allowed",
    ):
        invitations.create_invitation(
            privileged_settings,
            postgres_url=postgres_url,
            email="denied@not-allowed.example",
            role="member",
            invited_by=actor_id,
        )

    recipient = f"allowed-user@{allowed_domain}"
    created = invitations.create_invitation(
        privileged_settings,
        postgres_url=postgres_url,
        email=recipient,
        role="member",
        invited_by=actor_id,
        upload_enabled=True,
    )
    assert sent_recipients == [recipient]

    with psycopg.connect(postgres_url) as connection:
        invitation_row = connection.execute(
            """
            SELECT email, role::text, upload_enabled, revoked_at
            FROM app.team_invitations
            WHERE id = %s
            """,
            (created.invitation_id,),
        ).fetchone()
        audit_row = connection.execute(
            """
            SELECT payload
            FROM app.audit_events
            WHERE event_type = 'invitation.created'
              AND target_id = %s
            """,
            (created.invitation_id,),
        ).fetchone()
    assert invitation_row == (recipient, "member", True, None)
    assert audit_row is not None
    assert audit_row[0]["domain"] == allowed_domain
    assert created.raw_token not in str(audit_row[0])

    def fail_invite(
        _settings: PrivilegedAuthSettings,
        *,
        email: str,
        raw_token: str,
    ) -> None:
        """Simulate provider rejection after application persistence."""

        assert email
        assert raw_token
        raise invitations.InvitationServiceError("provider unavailable")

    monkeypatch.setattr(
        invitations,
        "send_provider_invite_email",
        fail_invite,
    )
    failed_recipient = f"delivery-failure@{allowed_domain}"
    with pytest.raises(
        invitations.InvitationServiceError,
        match="provider unavailable",
    ):
        invitations.create_invitation(
            privileged_settings,
            postgres_url=postgres_url,
            email=failed_recipient,
            role="viewer",
            invited_by=actor_id,
        )

    with psycopg.connect(postgres_url) as connection:
        failed_row = connection.execute(
            """
            SELECT revoked_at
            FROM app.team_invitations
            WHERE email = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (failed_recipient,),
        ).fetchone()
    assert failed_row is not None
    assert isinstance(failed_row[0], datetime)


def test_last_active_owner_cannot_be_offboarded(
    postgres_url: str,
    privileged_settings: PrivilegedAuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sole enabled owner remains a usable administrative recovery path."""

    sole_owner_id = uuid.uuid4()
    _insert_profile(
        postgres_url,
        user_id=sole_owner_id,
        email=f"sole-owner-{sole_owner_id}@example.com",
        role="owner",
        upload_enabled=False,
        mfa_enrolled=True,
    )
    with psycopg.connect(postgres_url) as connection:
        connection.execute(
            """
            UPDATE app.profiles
            SET disabled_at = timezone('utc', now())
            WHERE role = 'owner'::app.user_role
              AND user_id <> %s
              AND disabled_at IS NULL
            """,
            (sole_owner_id,),
        )
        connection.commit()

    provider_called = False

    def revoke_provider(
        _settings: PrivilegedAuthSettings,
        _user_id: uuid.UUID,
    ) -> None:
        """Record whether an unsafe provider mutation was attempted."""

        nonlocal provider_called
        provider_called = True

    monkeypatch.setattr(
        offboarding,
        "revoke_provider_sessions",
        revoke_provider,
    )
    with pytest.raises(
        offboarding.OffboardingError,
        match="last active owner",
    ):
        offboarding.apply_offboarding_security(
            privileged_settings,
            postgres_url,
            subject_user_id=sole_owner_id,
            requested_by=sole_owner_id,
            actor_role="owner",
            actor_assurance_level="aal2",
        )
    assert provider_called is False
