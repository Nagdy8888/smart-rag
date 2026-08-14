"""Holdout access tokens, denials, and auditable authorization."""

from __future__ import annotations

from dataclasses import dataclass

from smart_rag_core.settings.evaluation import (
    ALLOWED_HOLDOUT_PURPOSES,
    EvaluationSettings,
    load_evaluation_settings,
)


class HoldoutSealedError(PermissionError):
    """Raised when a caller requests holdout labels without authorization."""


@dataclass(frozen=True, slots=True)
class HoldoutAccess:
    """Explicit holdout access decision.

    Attributes:
        allowed: Whether sealed labels may be materialized.
        purpose: Allow-listed purpose when allowed.
        actor: Auditable actor when allowed.
    """

    allowed: bool
    purpose: str | None = None
    actor: str | None = None

    @classmethod
    def denied(cls) -> HoldoutAccess:
        """Return the default deny-by-default holdout decision.

        Returns:
            Access object with ``allowed=False``.
        """

        return cls(allowed=False)

    @classmethod
    def from_settings(cls, settings: EvaluationSettings | None = None) -> HoldoutAccess:
        """Build access from centralized evaluation settings.

        Args:
            settings: Optional preloaded settings. When omitted, settings are
                loaded from the process environment.

        Returns:
            Authorized access when the flag, purpose, and actor are valid;
            otherwise denied.
        """

        loaded = settings if settings is not None else load_evaluation_settings()
        if not loaded.holdout_access:
            return cls.denied()
        return cls(
            allowed=True,
            purpose=loaded.holdout_access_purpose,
            actor=loaded.holdout_access_actor,
        )


def assert_holdout_allowed(access: HoldoutAccess) -> None:
    """Raise when holdout materialization is not authorized.

    Args:
        access: Caller-supplied access decision.

    Raises:
        HoldoutSealedError: If access is denied or the purpose is not
            allow-listed.
    """

    if not access.allowed:
        raise HoldoutSealedError("holdout is sealed; default access is denied")
    if access.purpose not in ALLOWED_HOLDOUT_PURPOSES:
        raise HoldoutSealedError("holdout purpose is not allow-listed")
    if access.actor is None or access.actor.strip() == "":
        raise HoldoutSealedError("holdout actor is required")
