"""Typed crawl policy and adapter failures."""

from __future__ import annotations


class CrawlPolicyError(Exception):
    """Raised when a URL or hop fails SSRF/scope/limit checks."""

    def __init__(self, reason: str, *, code: str = "policy_denied") -> None:
        """Capture a safe failure reason for provenance."""

        super().__init__(reason)
        self.reason = reason
        self.code = code


class CrawlProxyError(Exception):
    """Raised when the restricted egress proxy rejects or fails a fetch."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        """Capture proxy failure metadata."""

        super().__init__(message)
        self.status_code = status_code


class CrawlLimitExceeded(CrawlPolicyError):
    """Raised when crawl-wide byte/page/depth/time bounds are exceeded."""

    def __init__(self, reason: str) -> None:
        """Mark a limit-specific denial."""

        super().__init__(reason, code="limit_exceeded")
