"""Canonical payload hashing for query-run idempotency."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.search_scope import RequestedSearchScope


def hash_query_admission_payload(
    *,
    conversation_id: UUID,
    route_family: Phase6RouteFamily,
    message: str,
    requested_search_scope: RequestedSearchScope = RequestedSearchScope.AUTO,
) -> str:
    """Return SHA-256 hex of the canonical admit payload.

    The idempotency key is intentionally excluded so the same key with a
    changed message, family, or non-auto search scope is a collision, not a
    reconnect. ``auto`` omits the new field so legacy Auto retries keep the
    old hash.

    Args:
        conversation_id: Conversation the run belongs to.
        route_family: Server-selected route family used for the envelope.
        message: User message text admitted with this key.
        requested_search_scope: Client source preference. ``auto`` is omitted
            from the canonical JSON.

    Returns:
        64-character lowercase hex digest.
    """

    payload: dict[str, str] = {
        "conversation_id": str(conversation_id),
        "message": message,
        "route_family": route_family.value,
    }
    if requested_search_scope is not RequestedSearchScope.AUTO:
        payload["requested_search_scope"] = requested_search_scope.value
    canonical = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
