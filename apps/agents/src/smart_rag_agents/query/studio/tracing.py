"""Apply LangSmith process flags for local LangGraph Studio.

Studio chats run in ``langgraph dev``, not the FastAPI API container.
The Agent Server only exports traces when ``LANGSMITH_API_KEY`` and
``LANGSMITH_TRACING`` are present in that process.
"""

from __future__ import annotations

from smart_rag_core.observability.langsmith_tracing import configure_langsmith
from smart_rag_core.settings import SettingsValidationError, load_agent_settings


def apply_studio_langsmith_flags() -> dict[str, str]:
    """Configure LangSmith hide/tracing flags for the Studio process.

    Returns:
        Applied non-secret flag names and values. Empty when settings
        cannot load (missing required Studio env).

    Side Effects:
        Mutates ``LANGSMITH_*`` and ``LANGCHAIN_TRACING_V2`` process
        environment keys when agent settings validate. Does not open a
        network connection. Never logs the API key.
    """

    try:
        settings = load_agent_settings()
    except (SettingsValidationError, ValueError):
        return {}
    return configure_langsmith(settings)
