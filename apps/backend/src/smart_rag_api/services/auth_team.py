"""Auth/team HTTP wrappers over existing invitation and offboarding services."""

from __future__ import annotations

import hashlib
from uuid import UUID

import psycopg
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.identity import CallerContext, UserRole
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
            assurance_level: JWT ``aal`` claim. Privileged/upload upgrades
                require AAL2.

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
        """Disable and revoke sessions for one subject. Owner/admin AAL2.

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


__all__ = [
    "AuthTeamService",
    "InvitationServiceError",
    "OffboardingError",
]
