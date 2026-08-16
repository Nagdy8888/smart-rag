"""Compact LangGraph store payloads: summaries and preferences only."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

FORBIDDEN_STORE_KEYS: frozenset[str] = frozenset(
    {"passage", "snippet", "html", "source"}
)
"""Keys that identify source-document copies. Store writes must reject them."""

_MAX_SUMMARY_CHARS = 2000
_MAX_PREFERENCE_CHARS = 500


class StorePayloadError(ValueError):
    """Raised when a store write would persist source documents or oversized text."""


def validate_memory_store_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Copy a compact summary/preferences payload or fail closed.

    Args:
        payload: Candidate JSON mapping for LangGraph store.

    Returns:
        A shallow-copied mapping containing only compact memory fields.

    Raises:
        StorePayloadError: When forbidden source keys are present, nested
            mappings include those keys, or values exceed compact bounds.

    Side Effects:
        None.
    """

    forbidden = _forbidden_keys(payload)
    if forbidden:
        raise StorePayloadError(
            "source_document_rejected:" + ",".join(sorted(forbidden))
        )
    compact: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, str) and len(value) > _MAX_SUMMARY_CHARS:
            raise StorePayloadError("payload_too_large")
        if key == "preferences" and isinstance(value, Mapping):
            compact[key] = _compact_preferences(cast(Mapping[str, object], value))
            continue
        compact[key] = value
    return compact


def memory_store_namespace(
    *,
    company_id: str | None,
    user_id: str,
    conversation_id: str,
) -> tuple[str, str, str]:
    """Return the LangGraph store namespace for one conversation.

    Args:
        company_id: Optional company identifier. V1 uses a single company.
        user_id: Conversation creator UUID string.
        conversation_id: Conversation UUID string. Also the checkpoint thread id.

    Returns:
        ``(company_id or "company", user_id, conversation_id)``.
    """

    company = company_id if company_id else "company"
    return (company, user_id, conversation_id)


def _forbidden_keys(payload: Mapping[str, object]) -> frozenset[str]:
    """Return forbidden source-document keys found in a mapping tree.

    Args:
        payload: JSON-like mapping.

    Returns:
        Matching key names (lowercased).
    """

    found: set[str] = set()
    for key, value in payload.items():
        lowered = key.lower()
        if lowered in FORBIDDEN_STORE_KEYS:
            found.add(lowered)
        if isinstance(value, Mapping):
            nested = _forbidden_keys(cast(Mapping[str, object], value))
            found.update(nested)
    return frozenset(found)


def _compact_preferences(payload: Mapping[str, object]) -> dict[str, object]:
    """Copy preference scalars with a character bound.

    Args:
        payload: Preference mapping.

    Returns:
        Compact preference copy.

    Raises:
        StorePayloadError: When a preference string is too large or nested
            mappings include source keys.
    """

    forbidden = _forbidden_keys(payload)
    if forbidden:
        raise StorePayloadError(
            "source_document_rejected:" + ",".join(sorted(forbidden))
        )
    compact: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, str) and len(value) > _MAX_PREFERENCE_CHARS:
            raise StorePayloadError("preference_too_large")
        compact[key] = value
    return compact
