"""Canonical payload hashing for query-run idempotency."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily


def hash_query_admission_payload(
    *,
    conversation_id: UUID,
    route_family: Phase6RouteFamily,
    message: str,
) -> str:
    """Return SHA-256 hex of the canonical admit payload.

    The idempotency key is intentionally excluded so the same key with a
    changed message or family is a collision, not a reconnect.

    Args:
        conversation_id: Conversation the run belongs to.
        route_family: Server-selected route family used for the envelope.
        message: User message text admitted with this key.

    Returns:
        64-character lowercase hex digest.
    """

    canonical = json.dumps(
        {
            "conversation_id": str(conversation_id),
            "message": message,
            "route_family": route_family.value,
        },
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
