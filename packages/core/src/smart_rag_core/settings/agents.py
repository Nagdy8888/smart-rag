"""Typed startup settings for the LangGraph agents deployable."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, SecretStr

from smart_rag_core.settings.base import SharedSettings, load_settings


class AgentSettings(SharedSettings):
    """Validated agent configuration.

    Attributes:
        service_name: Stable structured-log service identifier.
        langgraph_studio_live_enabled: Whether authenticated Studio live may
            open per-run resources. Default ``false``.
        langgraph_studio_access_token: Bearer JWT used by ``query_studio_live``.
            Secret. Never logged or represented in plaintext.
    """

    service_name: ClassVar[Literal["agents"]] = "agents"
    langgraph_studio_live_enabled: bool = Field(
        default=False,
        validation_alias="LANGGRAPH_STUDIO_LIVE_ENABLED",
        description=(
            "Enable authenticated query_studio_live execution. Default false. "
            "Enabled without LANGGRAPH_STUDIO_ACCESS_TOKEN rejects safely."
        ),
        json_schema_extra={"security": "public"},
    )
    langgraph_studio_access_token: SecretStr | None = Field(
        default=None,
        validation_alias="LANGGRAPH_STUDIO_ACCESS_TOKEN",
        description=(
            "Verified Supabase access token for query_studio_live. Never a "
            "service-role key. Omitted from repr, logs, traces, and state."
        ),
        json_schema_extra={"security": "secret"},
    )


def load_agent_settings() -> AgentSettings:
    """Load validated agent settings from the process environment.

    Returns:
        Validated agent settings.

    Raises:
        SettingsValidationError: If startup configuration is invalid.

    Side Effects:
        Reads environment variables through the shared settings boundary.
    """

    return load_settings(AgentSettings)
