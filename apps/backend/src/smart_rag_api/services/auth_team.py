"""Auth/team HTTP wrappers over existing invitation and offboarding services."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.security.untrusted import isolate_untrusted_text
from smart_rag_core.settings.base import SettingsValidationError

from smart_rag_api.auth_admin.invitations import (
    CreatedInvitation,
    InvitationServiceError,
    create_invitation,
)
from smart_rag_api.auth_admin.offboarding import (
    CompletedOffboarding,
    OffboardingError,
    apply_offboarding_security,
)
from smart_rag_api.auth_admin.settings import load_privileged_auth_settings


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    """One ``app.profiles`` row with Auth email when present.

    Attributes:
        user_id: Auth subject.
        email: Isolated Auth email, or empty when missing.
        display_name: Isolated optional profile name.
        role: Live ``app.user_role`` text.
        upload_enabled: Upload capability flag.
        disabled_at: Offboard timestamp when set.
        created_at: Profile creation time.
    """

    user_id: UUID
    email: str
    display_name: str | None
    role: str
    upload_enabled: bool
    disabled_at: datetime | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class PendingInvitation:
    """One unaccepted invitation. Token hash is never loaded.

    Attributes:
        invitation_id: Invitation row id.
        email: Isolated invitee email.
        role: Invited role text.
        upload_enabled: Upload flag on the invitation.
        expires_at: Expiry timestamp.
        created_at: Invitation creation time.
    """

    invitation_id: UUID
    email: str
    role: str
    upload_enabled: bool
    expires_at: datetime
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class WorkspaceDirectory:
    """Bounded owner/admin listing.

    Attributes:
        members: Up to 200 profiles.
        pending_invitations: Up to 200 unaccepted invitations.
    """

    members: tuple[WorkspaceMember, ...]
    pending_invitations: tuple[PendingInvitation, ...]


def _raise_team_rpc(exc: BaseException) -> NoReturn:
    """Map team RPC Postgres errors to admission reasons.

    Args:
        exc: Driver error.

    Raises:
        QueryAdmissionError: Always. ``forbidden`` or
            ``authorization_rejected`` when the SQL reason is present.
    """

    message = str(exc)
    if "team:forbidden" in message:
        raise QueryAdmissionError("forbidden") from exc
    if "team:authorization_rejected" in message:
        raise QueryAdmissionError("authorization_rejected") from exc
    raise QueryAdmissionError("database_rejected") from exc


def _optional_text(value: object) -> str | None:
    """Return isolated text or None.

    Args:
        value: Database field.

    Returns:
        Isolated string, or None when empty.
    """

    if value is None:
        return None
    text = isolate_untrusted_text(str(value)).strip()
    return text or None


class AuthTeamService:
    """Privileged Auth Admin HTTP adapter. Secrets load only on call."""

    def __init__(self, postgres_url: str) -> None:
        """Store the application Postgres URL.

        Args:
            postgres_url: app_api URL for accept; privileged settings load
                separately for invite/offboard.
        """

        self._postgres_url = postgres_url

    def create_invitation(
        self,
        caller: CallerContext,
        *,
        email: str,
        role: str,
        upload_enabled: bool,
    ) -> CreatedInvitation:
        """Create a 24-hour invitation. Owner/admin only.

        Args:
            caller: Authenticated caller.
            email: Invitee email.
            role: Target role.
            upload_enabled: Upload capability.

        Returns:
            Created invitation including the one-time token.

        Raises:
            QueryAdmissionError: Forbidden role or missing privileged secret.
            InvitationServiceError: Domain/policy/provider failure.
        """

        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
        try:
            settings = load_privileged_auth_settings()
        except SettingsValidationError as exc:
            raise QueryAdmissionError("limiter_unavailable") from exc
        return create_invitation(
            settings,
            postgres_url=self._postgres_url,
            email=email,
            role=role,
            invited_by=UUID(caller.user_id),
            upload_enabled=upload_enabled,
        )

    def accept_invitation(
        self,
        caller: CallerContext,
        *,
        raw_token: str,
        email: str,
        assurance_level: str = "aal1",
    ) -> UUID:
        """Accept a single-use invitation for the authenticated subject.

        Args:
            caller: Authenticated caller.
            raw_token: One-time invitation secret.
            email: Verified JWT/test email, never a client-trusted identity.
            assurance_level: Deprecated JWT ``aal`` claim. Ignored; retained
                for the additive RPC signature.

        Returns:
            Invitation id.

        Raises:
            QueryAdmissionError: Missing email or RPC rejection.
        """

        if not email:
            raise QueryAdmissionError("authorization_rejected")
        digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT app.accept_invitation(%s, %s, %s, %s)",
                        (
                            digest,
                            caller.user_id,
                            email.strip().lower(),
                            assurance_level,
                        ),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg.Error as exc:
            raise QueryAdmissionError("authorization_rejected") from exc
        if row is None:
            raise QueryAdmissionError("not_found")
        return UUID(str(row[0]))

    def offboard(
        self,
        caller: CallerContext,
        *,
        subject_user_id: UUID,
        assurance_level: str,
    ) -> CompletedOffboarding:
        """Disable and revoke sessions for one subject. Owner/admin only.

        Args:
            caller: Authenticated caller.
            subject_user_id: User to offboard.
            assurance_level: JWT ``aal`` claim.

        Returns:
            Completed offboarding record.

        Raises:
            QueryAdmissionError: Forbidden or missing privileged secret.
            OffboardingError: Provider/SQL failure.
        """

        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
        try:
            settings = load_privileged_auth_settings()
        except SettingsValidationError as exc:
            raise QueryAdmissionError("limiter_unavailable") from exc
        return apply_offboarding_security(
            settings,
            self._postgres_url,
            subject_user_id=subject_user_id,
            requested_by=UUID(caller.user_id),
            actor_role=caller.rpc_role(),
            actor_assurance_level=assurance_level,
        )

    def list_directory(self, caller: CallerContext) -> WorkspaceDirectory:
        """List workspace profiles and unaccepted invitations.

        Args:
            caller: Authenticated caller.

        Returns:
            Bounded directory. Token hashes are never selected.

        Raises:
            QueryAdmissionError: Members/viewers, stale caller, or database
                rejection.
        """

        if caller.role not in {UserRole.OWNER, UserRole.ADMIN}:
            raise QueryAdmissionError("forbidden")
        try:
            with psycopg.connect(self._postgres_url) as connection:
                connection.execute("SET ROLE app_api")
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """
                        SELECT * FROM app.list_workspace_members(%s, %s, %s)
                        """,
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                        ),
                    )
                    member_rows = cursor.fetchall()
                    cursor.execute(
                        """
                        SELECT * FROM app.list_pending_team_invitations(
                          %s, %s, %s
                        )
                        """,
                        (
                            caller.user_id,
                            caller.rpc_role(),
                            caller.rpc_authorization_version(),
                        ),
                    )
                    invitation_rows = cursor.fetchall()
        except psycopg.Error as exc:
            _raise_team_rpc(exc)
        members: list[WorkspaceMember] = []
        for row in member_rows:
            disabled = row.get("disabled_at")
            created = row.get("created_at")
            members.append(
                WorkspaceMember(
                    user_id=UUID(str(row["user_id"])),
                    email=isolate_untrusted_text(str(row.get("email") or "")),
                    display_name=_optional_text(row.get("display_name")),
                    role=str(row.get("role") or ""),
                    upload_enabled=bool(row.get("upload_enabled")),
                    disabled_at=disabled if isinstance(disabled, datetime) else None,
                    created_at=created if isinstance(created, datetime) else None,
                )
            )
        invitations: list[PendingInvitation] = []
        for row in invitation_rows:
            expires = row.get("expires_at")
            if not isinstance(expires, datetime):
                continue
            created = row.get("created_at")
            invitations.append(
                PendingInvitation(
                    invitation_id=UUID(str(row["invitation_id"])),
                    email=isolate_untrusted_text(str(row.get("email") or "")),
                    role=str(row.get("role") or ""),
                    upload_enabled=bool(row.get("upload_enabled")),
                    expires_at=expires,
                    created_at=created if isinstance(created, datetime) else None,
                )
            )
        return WorkspaceDirectory(
            members=tuple(members),
            pending_invitations=tuple(invitations),
        )


__all__ = [
    "AuthTeamService",
    "InvitationServiceError",
    "OffboardingError",
    "PendingInvitation",
    "WorkspaceDirectory",
    "WorkspaceMember",
]
