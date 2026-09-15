"""Typed fail-closed reasons for the Web research subgraph."""

from __future__ import annotations

_WEB_REASONS = frozenset(
    {
        "web_search_disabled",
        "web_search_unconfigured",
        "web_search_auth_failed",
        "web_search_quota_exhausted",
        "web_search_rate_limited",
        "web_search_timeout",
        "web_search_transport_failed",
        "web_search_invalid_response",
        "web_evidence_insufficient",
        "web_content_unavailable",
        "web_operation:ambiguous",
        "web_operation:conflict",
        "company_passage_forbidden",
        "cancelled",
        "web_round_exhausted",
    }
)


class WebResearchError(RuntimeError):
    """Safe machine-readable Web research failure.

    Args:
        reason: Published reason code. Never includes keys, queries,
            excerpts, or result URLs.
    """

    def __init__(self, reason: str) -> None:
        """Store one safe reason.

        Args:
            reason: Stable ``web_*`` or ``web_search_*`` code.

        Raises:
            ValueError: If ``reason`` is not published.
        """

        if reason not in _WEB_REASONS:
            raise ValueError("unsupported_web_research_reason")
        super().__init__(reason)
        self.reason = reason

    def __repr__(self) -> str:
        """Return a key-free representation."""

        return f"WebResearchError(reason={self.reason!r})"
