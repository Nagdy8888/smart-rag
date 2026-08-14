"""Versioned prompt definitions owned by the agents package."""

from __future__ import annotations

from pathlib import Path

QUERY_PROFILE_PROMPT_VERSION = "query_profile_v1"
QUERY_PROFILE_PROMPT_PATH = Path(__file__).resolve().parent / "query_profile_v1.md"
RERANK_PROMPT_VERSION = "rerank_v1"
RERANK_PROMPT_PATH = Path(__file__).resolve().parent / "rerank_v1.md"


def query_profile_prompt_text() -> str:
    """Return the Packet 3 query-profile prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return QUERY_PROFILE_PROMPT_PATH.read_text(encoding="utf-8")


def rerank_prompt_text() -> str:
    """Return the Packet 5 rerank prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return RERANK_PROMPT_PATH.read_text(encoding="utf-8")
