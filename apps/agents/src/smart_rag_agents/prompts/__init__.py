"""Versioned prompt definitions owned by the agents package."""

from __future__ import annotations

from pathlib import Path

QUERY_PROFILE_PROMPT_VERSION = "query_profile_v1"
QUERY_PROFILE_PROMPT_PATH = Path(__file__).resolve().parent / "query_profile_v1.md"
RERANK_PROMPT_VERSION = "rerank_v2"
RERANK_PROMPT_PATH = Path(__file__).resolve().parent / "rerank_v2.md"
ANSWER_PROMPT_VERSION = "answer_v12"
ANSWER_PROMPT_PATH = Path(__file__).resolve().parent / "answer_v12.md"
ORGANIZE_PROMPT_VERSION = "organize_v1"
ORGANIZE_PROMPT_PATH = Path(__file__).resolve().parent / "organize_v1.md"
GENERAL_CHAT_PROMPT_VERSION = "general_chat_v2"
GENERAL_CHAT_PROMPT_PATH = Path(__file__).resolve().parent / "general_chat_v2.md"
VERIFIER_PROMPT_VERSION = "verifier_v5"
VERIFIER_PROMPT_PATH = Path(__file__).resolve().parent / "verifier_v5.md"
OPTIONAL_CATALOG_PROMPT_VERSION = "optional_catalog_v1"
OPTIONAL_CATALOG_PROMPT_PATH = (
    Path(__file__).resolve().parent / "optional_catalog_v1.md"
)
SUMMARY_PROMPT_VERSION = "summary_v1"
SUMMARY_PROMPT_PATH = Path(__file__).resolve().parent / "summary_v1.md"
CONVERSATION_TITLE_PROMPT_VERSION = "conversation_title_v1"
CONVERSATION_TITLE_PROMPT_PATH = (
    Path(__file__).resolve().parent / "conversation_title_v1.md"
)
EVAL_PDF_JUDGE_PROMPT_VERSION = "eval_pdf_judge_v1"
EVAL_PDF_JUDGE_PROMPT_PATH = Path(__file__).resolve().parent / "eval_pdf_judge_v1.md"
WEB_CRITIQUE_PROMPT_VERSION = "web_critique_v1"
WEB_CRITIQUE_PROMPT_PATH = Path(__file__).resolve().parent / "web_critique_v1.md"
WEB_ANSWER_PROMPT_VERSION = "web_answer_v1"
WEB_ANSWER_PROMPT_PATH = Path(__file__).resolve().parent / "web_answer_v1.md"


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


def organize_prompt_text() -> str:
    """Return the verified-answer rewrite prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return ORGANIZE_PROMPT_PATH.read_text(encoding="utf-8")


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


def conversation_title_prompt_text() -> str:
    """Return the session-title prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return CONVERSATION_TITLE_PROMPT_PATH.read_text(encoding="utf-8")


def eval_pdf_judge_prompt_text() -> str:
    """Return the private-PDF judge prompt. Never reuse ``eval_judge_v1``.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return EVAL_PDF_JUDGE_PROMPT_PATH.read_text(encoding="utf-8")


def web_critique_prompt_text() -> str:
    """Return the Web research critique prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return WEB_CRITIQUE_PROMPT_PATH.read_text(encoding="utf-8")


def web_answer_prompt_text() -> str:
    """Return the Web research synthesis prompt body.

    Returns:
        Markdown prompt text.

    Raises:
        OSError: If the prompt file is missing.
    """

    return WEB_ANSWER_PROMPT_PATH.read_text(encoding="utf-8")
