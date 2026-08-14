"""Typed settings for Phase 4 dataset access and holdout isolation."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from smart_rag_core.settings.base import load_settings

ALLOWED_HOLDOUT_PURPOSES = frozenset(
    {
        "packet8_immutable_holdout",
        "dataset_seal_verify",
    }
)


class EvaluationSettings(BaseSettings):
    """Holdout-access gates for evaluation tooling.

    Attributes:
        holdout_access: Whether sealed holdout labels may be materialized.
            Defaults to denied. From ``SMART_RAG_HOLDOUT_ACCESS``.
        holdout_access_purpose: Allow-listed purpose required when access is
            enabled. From ``SMART_RAG_HOLDOUT_ACCESS_PURPOSE``.
        holdout_access_actor: Auditable actor identifier required when access
            is enabled. From ``SMART_RAG_HOLDOUT_ACCESS_ACTOR``.
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    holdout_access: bool = Field(
        default=False,
        validation_alias="SMART_RAG_HOLDOUT_ACCESS",
        description="Enable sealed holdout materialization; default denied.",
        json_schema_extra={"security": "public"},
    )
    holdout_access_purpose: str | None = Field(
        default=None,
        validation_alias="SMART_RAG_HOLDOUT_ACCESS_PURPOSE",
        min_length=1,
        max_length=64,
        description="Allow-listed holdout access purpose.",
        json_schema_extra={"security": "internal"},
    )
    holdout_access_actor: str | None = Field(
        default=None,
        validation_alias="SMART_RAG_HOLDOUT_ACCESS_ACTOR",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="Auditable actor for authorized holdout access.",
        json_schema_extra={"security": "internal"},
    )

    @model_validator(mode="after")
    def require_purpose_and_actor_when_enabled(self) -> EvaluationSettings:
        """Reject enabled holdout access that lacks purpose or actor.

        Returns:
            The validated settings instance.

        Raises:
            ValueError: If access is enabled without an allow-listed purpose
                and actor, or if the purpose is unknown.
        """

        if not self.holdout_access:
            return self
        if self.holdout_access_purpose is None or self.holdout_access_actor is None:
            raise ValueError(
                "SMART_RAG_HOLDOUT_ACCESS_PURPOSE and "
                "SMART_RAG_HOLDOUT_ACCESS_ACTOR are required when "
                "SMART_RAG_HOLDOUT_ACCESS=true"
            )
        if self.holdout_access_purpose not in ALLOWED_HOLDOUT_PURPOSES:
            raise ValueError("holdout access purpose is not allow-listed")
        return self


def load_evaluation_settings() -> EvaluationSettings:
    """Load dataset-access settings from the process environment.

    Returns:
        Validated evaluation settings. Holdout remains denied unless both the
        flag and allow-listed purpose/actor are present.

    Raises:
        SettingsValidationError: If enabled access is missing purpose/actor.

    Side Effects:
        Reads process environment through Pydantic Settings.
    """

    return load_settings(EvaluationSettings)
