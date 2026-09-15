"""URL and span policy for persisted Web evidence."""

from __future__ import annotations

import hashlib

from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError
from smart_rag_core.ingestion.crawl.policy import normalize_url
from smart_rag_core.web_research.models import WebCitation


def normalize_web_url(raw_url: str) -> str:
    """Normalize a public HTTP(S) URL for persistence.

    Args:
        raw_url: Provider URL.

    Returns:
        Canonical URL.

    Raises:
        ValueError: If crawl policy rejects the URL.
    """

    try:
        return normalize_url(raw_url).normalized
    except CrawlPolicyError as exc:
        raise ValueError("web_evidence:invalid_url") from exc


def excerpt_sha256(excerpt: str) -> str:
    """Hash excerpt bytes with SHA-256.

    Args:
        excerpt: Stored excerpt text.

    Returns:
        64-character hex digest.
    """

    return hashlib.sha256(excerpt.encode("utf-8")).hexdigest()


def assert_span_contained(*, excerpt: str, citation: WebCitation) -> None:
    """Require the citation span to be an exact substring of the excerpt.

    Args:
        excerpt: Persisted source excerpt.
        citation: Candidate citation.

    Raises:
        ValueError: If the span is missing from the excerpt.
    """

    if citation.span not in excerpt:
        raise ValueError("web_evidence:span_not_contained")
