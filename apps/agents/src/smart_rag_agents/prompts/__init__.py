"""Versioned prompt definitions owned by the agents package."""

from __future__ import annotations

from pathlib import Path

QUERY_PROFILE_PROMPT_VERSION = "query_profile_v1"
QUERY_PROFILE_PROMPT_PATH = Path(__file__).resolve().parent / "query_profile_v1.md"
RERANK_PROMPT_VERSION = "rerank_v1"
RERANK_PROMPT_PATH = Path(__file__).resolve().parent / "rerank_v1.md"
ANSWER_PROMPT_VERSION = "answer_v1"
ANSWER_PROMPT_PATH = Path(__file__).resolve().parent / "answer_v1.md"
GENERAL_CHAT_PROMPT_VERSION = "general_chat_v1"
GENERAL_CHAT_PROMPT_PATH = Path(__file__).resolve().parent / "general_chat_v1.md"
VERIFIER_PROMPT_VERSION = "verifier_v1"
VERIFIER_PROMPT_PATH = Path(__file__).resolve().parent / "verifier_v1.md"
OPTIONAL_CATALOG_PROMPT_VERSION = "optional_catalog_v1"
OPTIONAL_CATALOG_PROMPT_PATH = (
    Path(__file__).resolve().parent / "optional_catalog_v1.md"
)
SUMMARY_PROMPT_VERSION = "summary_v1"
SUMMARY_PROMPT_PATH = Path(__file__).resolve().parent / "summary_v1.md"


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


def answer_prompt_text() -> str:
    """Return the Packet 3 canonical answer prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return ANSWER_PROMPT_PATH.read_text(encoding="utf-8")


def general_chat_prompt_text() -> str:
    """Return the Packet 12 no-source general-chat prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return GENERAL_CHAT_PROMPT_PATH.read_text(encoding="utf-8")


def verifier_prompt_text() -> str:
    """Return the Packet 3 atomic-link verifier prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return VERIFIER_PROMPT_PATH.read_text(encoding="utf-8")


def optional_catalog_prompt_text() -> str:
    """Return the Packet 4 Level 0 optional-catalog prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return OPTIONAL_CATALOG_PROMPT_PATH.read_text(encoding="utf-8")


def summary_prompt_text() -> str:
    """Return the Packet 7 compact summary prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return SUMMARY_PROMPT_PATH.read_text(encoding="utf-8")
