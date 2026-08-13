"""Deterministic content normalization for deduplication."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_dedup(text: str) -> str:
    """Normalize passage text for exact duplicate hashing.

    Args:
        text: Raw passage text.

    Returns:
        Lowercased, whitespace-collapsed Unicode-normalized form.
    """

    normalized = unicodedata.normalize("NFKC", text.strip().lower())
    return _WHITESPACE_RE.sub(" ", normalized)


def content_hash(text: str) -> str:
    """Compute normalized SHA-256 digest for exact deduplication.

    Args:
        text: Raw passage text.

    Returns:
        Lowercase hex SHA-256 of the normalized form.
    """

    payload = normalize_for_dedup(text)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
