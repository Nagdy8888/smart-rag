"""Typed startup settings for the LangGraph agents deployable."""

from __future__ import annotations

from typing import ClassVar, Literal

from smart_rag_core.settings.base import SharedSettings, load_settings


class AgentSettings(SharedSettings):
    """Validated agent configuration.

    Attributes:
        service_name: Stable structured-log service identifier.
    """

    service_name: ClassVar[Literal["agents"]] = "agents"


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
