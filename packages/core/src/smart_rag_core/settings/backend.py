"""Typed startup settings for the FastAPI backend deployable."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from smart_rag_core.settings.base import SharedSettings, load_settings


class BackendSettings(SharedSettings):
    """Validated backend configuration.

    Attributes:
        service_name: Stable structured-log service identifier.
        bind_host: HTTP bind address from ``API_BIND_HOST``. Public, default
            ``0.0.0.0``.
        bind_port: HTTP bind port from ``API_BIND_PORT``. Public, default
            ``8000``.
    """

    service_name: ClassVar[Literal["backend"]] = "backend"
    bind_host: str = Field(
        default="0.0.0.0",  # noqa: S104 - container HTTP listener default
        validation_alias="API_BIND_HOST",
        min_length=1,
        max_length=255,
        description="Backend HTTP bind address.",
        json_schema_extra={"security": "public"},
    )
    bind_port: int = Field(
        default=8000,
        validation_alias="API_BIND_PORT",
        ge=1,
        le=65535,
        description="Backend HTTP bind port.",
        json_schema_extra={"security": "public"},
    )


def load_backend_settings() -> BackendSettings:
    """Load validated backend settings from the process environment.

    Returns:
        Validated backend settings.

    Raises:
        SettingsValidationError: If startup configuration is invalid.

    Side Effects:
        Reads environment variables through the shared settings boundary.
    """

    return load_settings(BackendSettings)
