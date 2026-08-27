"""OpenAI model identifiers loaded from environment variables.

``OPENAI_CHAT_MODEL_ID`` is the default for every chat-style call (profile,
answer, verifier, rerank, LightRAG LLM, conversation title, eval judge).
Per-role overrides use ``OPENAI_<ROLE>_MODEL_ID`` when set.

``OPENAI_EMBEDDING_MODEL`` pins hybrid retrieval and ingestion embeddings.
``EMBEDDING_DIMENSIONS`` stays code-pinned at 1024 per ADR; it is not env-driven.
"""

from __future__ import annotations

from smart_rag_core.settings.base import get_process_environ

DEFAULT_CHAT_MODEL_ID = "gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"


def _optional_env(name: str) -> str | None:
    """Return a trimmed env value or ``None`` when unset or blank.

    Args:
        name: Process environment variable name.

    Returns:
        Non-empty trimmed value, or ``None``.
    """

    value = get_process_environ(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _resolve_chat_model_id(role_env: str) -> str:
    """Resolve one chat model id from a role override or the shared default.

    Args:
        role_env: Role-specific override variable name.

    Returns:
        Allow-listed chat model identifier for the role.
    """

    return (
        _optional_env(role_env)
        or _optional_env("OPENAI_CHAT_MODEL_ID")
        or DEFAULT_CHAT_MODEL_ID
    )


OPENAI_CHAT_MODEL_ID = _optional_env("OPENAI_CHAT_MODEL_ID") or DEFAULT_CHAT_MODEL_ID
OPENAI_EMBEDDING_MODEL = (
    _optional_env("OPENAI_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
)

PROFILE_MODEL_ID = _resolve_chat_model_id("OPENAI_PROFILE_MODEL_ID")
ANSWER_MODEL_ID = _resolve_chat_model_id("OPENAI_ANSWER_MODEL_ID")
VERIFIER_MODEL_ID = _resolve_chat_model_id("OPENAI_VERIFIER_MODEL_ID")
CONVERSATION_TITLE_MODEL_ID = _resolve_chat_model_id(
    "OPENAI_CONVERSATION_TITLE_MODEL_ID"
)
EVAL_JUDGE_MODEL_ID = _resolve_chat_model_id("OPENAI_EVAL_JUDGE_MODEL_ID")
RERANK_MODEL_ID = _resolve_chat_model_id("OPENAI_RERANK_MODEL_ID")
LIGHTRAG_LLM_MODEL_ID = _resolve_chat_model_id("OPENAI_LIGHTRAG_MODEL_ID")

EMBEDDING_MODEL = OPENAI_EMBEDDING_MODEL

ALLOWED_PROFILE_MODEL_IDS = frozenset({PROFILE_MODEL_ID})
ALLOWED_ANSWER_MODEL_IDS = frozenset({ANSWER_MODEL_ID})
ALLOWED_VERIFIER_MODEL_IDS = frozenset({VERIFIER_MODEL_ID})
ALLOWED_CONVERSATION_TITLE_MODEL_IDS = frozenset({CONVERSATION_TITLE_MODEL_ID})
ALLOWED_EVAL_JUDGE_MODEL_IDS = frozenset({EVAL_JUDGE_MODEL_ID})
ALLOWED_RERANK_MODEL_IDS = frozenset({RERANK_MODEL_ID})
ALLOWED_LIGHTRAG_LLM_MODEL_IDS = frozenset({LIGHTRAG_LLM_MODEL_ID})
