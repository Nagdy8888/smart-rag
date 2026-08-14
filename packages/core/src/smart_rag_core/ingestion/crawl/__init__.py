"""Bounded approved website crawl adapters.

Eager exception/limit exports avoid importing ``adapter`` (and therefore
``gateways.crawl_proxy``) for fail-closed policy callers. Import adapter
symbols from ``smart_rag_core.ingestion.crawl.adapter``.
"""

from smart_rag_core.ingestion.crawl.exceptions import (
    CrawlLimitExceeded,
    CrawlPolicyError,
    CrawlProxyError,
)
from smart_rag_core.ingestion.crawl.limits import CRAWL_POLICY_VERSION

__all__ = [
    "CRAWL_POLICY_VERSION",
    "CrawlLimitExceeded",
    "CrawlPolicyError",
    "CrawlProxyError",
]
