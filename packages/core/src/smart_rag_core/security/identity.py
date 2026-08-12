"""Server-derived caller identity for transaction-pool-safe Postgres RPC context."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field


class UserRole(StrEnum):
    """Authoritative company roles stored in ``app.profiles.role``."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class CallerContext(BaseModel):
    """Typed RPC caller snapshot resolved server-side from JWT + profile state.

    FastAPI must populate every field from verified auth and a live profile read.
    Client-supplied role or authorization version claims are never trusted.
    Transaction-pooled API paths pass these values as explicit RPC arguments;
    session GUCs are not used for identity propagation.

    Attributes:
        user_id: Authenticated subject UUID from verified JWT ``sub``.
        role: Current ``app.profiles.role`` for the active membership.
        authorization_version: Monotonic company snapshot from
            ``app.company_settings.authorization_version``.
        session_id: Optional refresh-session identifier for revocation checks.
        disabled: Whether ``app.profiles.disabled_at`` is set.
        upload_enabled: Upload capability flag from profile (MFA enforced upstream).
        mfa_enrolled: Whether the profile records enrolled MFA.
    """

    model_config = ConfigDict(frozen=True, strict=True)

    user_id: str = Field(min_length=36, max_length=36)
    role: UserRole
    authorization_version: int = Field(ge=1)
    session_id: str | None = None
    disabled: bool = False
    upload_enabled: bool = False
    mfa_enrolled: bool = False

    def rpc_user_id(self) -> str:
        """Return the UUID string passed to security-invoker RPCs."""

        return self.user_id

    def rpc_role(self) -> str:
        """Return the role string passed to security-invoker RPCs."""

        return self.role.value

    def rpc_authorization_version(self) -> int:
        """Return the authorization snapshot passed to security-invoker RPCs."""

        return self.authorization_version

    def is_active(self) -> bool:
        """Return whether the caller may invoke protected RPCs."""

        return not self.disabled

    @classmethod
    def from_profile_row(
        cls,
        *,
        user_id: str,
        role: str,
        authorization_version: int,
        session_id: str | None = None,
        disabled_at: object | None = None,
        upload_enabled: bool = False,
        mfa_enrolled: bool = False,
    ) -> Self:
        """Build a caller context from authoritative profile and company rows.

        Args:
            user_id: Profile primary key UUID string.
            role: ``app.profiles.role`` enum text.
            authorization_version: Live company authorization snapshot.
            session_id: Optional session identifier for revocation checks.
            disabled_at: Profile ``disabled_at`` timestamp when set.
            upload_enabled: Profile upload capability flag.
            mfa_enrolled: Profile MFA enrollment flag.

        Returns:
            Immutable ``CallerContext`` suitable for RPC argument binding.

        Raises:
            ValueError: When ``role`` is not a supported ``UserRole`` value.
        """

        return cls(
            user_id=user_id,
            role=UserRole(role),
            authorization_version=authorization_version,
            session_id=session_id,
            disabled=disabled_at is not None,
            upload_enabled=upload_enabled,
            mfa_enrolled=mfa_enrolled,
        )
