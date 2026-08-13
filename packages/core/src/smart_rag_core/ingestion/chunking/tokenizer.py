"""Pinned embedding tokenizer for passage sizing."""

from __future__ import annotations

import tiktoken

from smart_rag_core.ingestion.chunking.limits import TOKENIZER_VERSION

_ENCODING_NAME = "cl100k_base"
_encoding = tiktoken.get_encoding(_ENCODING_NAME)


def count_tokens(text: str) -> int:
    """Count tokens under the pinned cl100k_base embedding tokenizer.

    Args:
        text: UTF-8 passage text.

    Returns:
        Non-negative token count for sizing and overlap.
    """

    if not text:
        return 0
    return len(_encoding.encode(text, disallowed_special=()))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to at most ``max_tokens`` without splitting surrogate pairs.

    Args:
        text: Source passage.
        max_tokens: Maximum allowed tokens.

    Returns:
        Prefix of ``text`` whose token count is ``<= max_tokens``.
    """

    if max_tokens <= 0 or not text:
        return ""
    tokens = _encoding.encode(text, disallowed_special=())
    if len(tokens) <= max_tokens:
        return text
    return _encoding.decode(tokens[:max_tokens])


def tail_tokens(text: str, token_count: int) -> str:
    """Return the trailing ``token_count`` tokens of ``text``.

    Args:
        text: Source passage.
        token_count: Number of trailing tokens to keep.

    Returns:
        Suffix whose token length is ``<= token_count``.
    """

    if token_count <= 0 or not text:
        return ""
    tokens = _encoding.encode(text, disallowed_special=())
    if len(tokens) <= token_count:
        return text
    return _encoding.decode(tokens[-token_count:])


def tokenizer_version() -> str:
    """Return the pinned tokenizer version identifier."""

    return TOKENIZER_VERSION
