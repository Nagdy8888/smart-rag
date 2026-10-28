"""Injectable ports for Exa, crawl-proxy fallback, and operation persistence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from smart_rag_core.gateways.exa_search import ExaContentsResponse, ExaSearchResponse
from smart_rag_core.web_research.models import WebOperationState, WebSourceRecord

ProgressEmitter = Callable[[str], None]
CancelCheck = Callable[[], bool]
DeadlineSeconds = Callable[[], float]


class WebSearchPort(Protocol):
    """Exa search and contents. Constructed outside graph nodes."""

    def search(
        self,
        *,
        query: str,
        remaining_deadline_seconds: float,
        num_results: int,
    ) -> ExaSearchResponse:
        """Run one bounded search.

        Args:
            query: Sanitized user text only.
            remaining_deadline_seconds: Remaining run deadline.
            num_results: Clamped to 1-12.

        Returns:
            Candidates and allow-listed contents URLs.
        """

        ...

    def get_contents(
        self,
        *,
        urls: tuple[str, ...],
        allowed_urls: frozenset[str],
        remaining_deadline_seconds: float,
    ) -> ExaContentsResponse:
        """Fetch contents for current-run candidate URLs only.

        Args:
            urls: Unique HTTP(S) URLs, at most six.
            allowed_urls: URLs returned by this run's searches.
            remaining_deadline_seconds: Remaining run deadline.

        Returns:
            Bounded page texts.
        """

        ...

    def aclose(self) -> None:
        """Close the HTTP client. Must not leak the API key."""

        ...


class CandidateFetchPort(Protocol):
    """Crawl-proxy fallback for missing candidate text or requested metadata."""

    def fetch_text(
        self,
        url: str,
        *,
        allowed_urls: frozenset[str],
    ) -> str | None:
        """Return excerpt text or ``None`` when the fetch fails.

        Args:
            url: Candidate URL.
            allowed_urls: Current-run Exa URLs. Non-members must not fetch.

        Returns:
            Excerpt text, or ``None``.
        """

        ...


class WebOperationStore(Protocol):
    """Idempotent P06-39 operation and source persistence."""

    def begin(
        self,
        *,
        operation_key: str,
        kind: str,
        request_hash: str,
    ) -> WebOperationState:
        """Begin or replay one operation."""

        ...

    def mark_sent(self, *, operation_id: str) -> WebOperationState:
        """Mark planned as sent. Ambiguous must not be retried."""

        ...

    def complete(
        self,
        *,
        operation_id: str,
        ok: bool,
        failure_reason: str | None = None,
    ) -> WebOperationState:
        """Complete a sent operation."""

        ...

    def insert_source(
        self,
        *,
        source_index: int,
        url: str,
        title: str,
        excerpt: str,
        published_date: str | None = None,
    ) -> WebSourceRecord:
        """Persist one source after URL policy."""

        ...
