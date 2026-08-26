"""SSE mapper catalog fields and fail-closed event assertions."""

from __future__ import annotations

from typing import Final

from smart_rag_core.sse.catalog import ALLOWED_SSE_EVENT_TYPES

GENERATE_ANSWER_NODE: Final[str] = "generate_answer"
GENERAL_SCOPE_NODE: Final[str] = "general_scope"
MIXED_SCOPE_NODE: Final[str] = "mixed_scope"
DRAFT_ANSWER_NODES: Final[frozenset[str]] = frozenset(
    {GENERATE_ANSWER_NODE, GENERAL_SCOPE_NODE, MIXED_SCOPE_NODE}
)
VERIFY_ANSWER_NODE: Final[str] = "verify_answer"
TOKEN_DELTA_LIMIT: Final[int] = 4096
ALLOWED_SSE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "stage",
        "status",
        "code",
        "reason",
        "route_family",
        "from_route",
        "to_route",
        "delta",
        "citation_ids",
        "ranks",
        "origin",
        "prompt_tokens",
        "completion_tokens",
        "tool_keys",
        "sse_schema_version",
    }
)
PARTIAL_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "verified_partial",
        "insufficient_evidence",
        "refused",
    }
)
REJECT_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "admission_rejected",
        "routing_rejected",
    }
)


def assert_catalog_event(event_type: str, payload: dict[str, object]) -> None:
    """Fail closed when a mapper draft leaves the SSE catalog.

    Args:
        event_type: Draft event name.
        payload: Draft payload.

    Raises:
        ValueError: Unknown type or disallowed payload key.
    """

    if event_type not in ALLOWED_SSE_EVENT_TYPES:
        raise ValueError("sse_event_not_allowlisted")
    extra = set(payload) - ALLOWED_SSE_FIELDS
    if extra:
        raise ValueError("sse_payload_field_not_allowlisted")
