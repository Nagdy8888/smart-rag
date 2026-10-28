"""Crawl-proxy fallback that may fetch only current-run Exa candidate URLs."""

from __future__ import annotations

import re
import time
from html import unescape

from smart_rag_core.gateways.crawl_proxy import CrawlProxyGateway, ProxyFetchRequest
from smart_rag_core.ingestion.crawl.dns import resolve_hostname
from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError, CrawlProxyError
from smart_rag_core.ingestion.crawl.policy import normalize_url
from smart_rag_core.web_research.exceptions import WebResearchError

_SCRIPT = re.compile(r"(?is)<script.*?</script>")
_STYLE = re.compile(r"(?is)<style.*?</style>")
_TAG = re.compile(r"(?s)<[^>]+>")
_SPACE = re.compile(r"\s+")


def html_to_excerpt(body: bytes) -> str:
    """Decode a page body into a bounded plaintext excerpt.

    Args:
        body: Proxy-decoded bytes.

    Returns:
        Whitespace-collapsed bounded text; the executor selects the retained 8K window.
    """

    text = body.decode("utf-8", errors="replace")
    text = _SCRIPT.sub(" ", text)
    text = _STYLE.sub(" ", text)
    text = _TAG.sub(" ", text)
    text = unescape(text)
    return _SPACE.sub(" ", text).strip()[:200_000]


class CrawlProxyCandidateFetch:
    """Fetch one Exa-allow-listed URL through the crawl proxy.

    API/agent code never opens ``httpx`` to the result URL.

    Args:
        proxy: Injected crawl-proxy client.
    """

    def __init__(self, proxy: CrawlProxyGateway) -> None:
        """Bind the proxy gateway.

        Args:
            proxy: Process-injected ``CrawlProxyGateway``.
        """

        self._proxy = proxy

    def fetch_text(
        self,
        url: str,
        *,
        allowed_urls: frozenset[str],
        remaining_deadline_seconds: float | None = None,
    ) -> str | None:
        """Fetch excerpt text only when ``url`` is an Exa candidate.

        Args:
            remaining_deadline_seconds: Optional caller budget for proxy work.
            url: Candidate URL.
            allowed_urls: Current-run Exa URLs.

        Returns:
            Excerpt, or ``None`` on policy/proxy failure.

        Raises:
            WebResearchError: If ``url`` was not an Exa candidate.
        """

        if url not in allowed_urls:
            raise WebResearchError("web_search_invalid_response")
        started = time.monotonic()
        try:
            normalized = normalize_url(url)
            dns = (
                resolve_hostname(
                    normalized.host,
                    timeout_seconds=min(2.0, remaining_deadline_seconds / 2),
                )
                if remaining_deadline_seconds is not None
                else resolve_hostname(normalized.host)
            )
            pin_ip = dns.pinned_ips[0]
            request = ProxyFetchRequest(
                url=normalized.normalized,
                method="GET",
                host_header=normalized.host,
                pin_ip=pin_ip,
                port=normalized.port,
                use_tls=normalized.scheme == "https",
                headers={"Accept": "text/html,text/plain,application/xhtml+xml"},
            )
            remaining = (
                max(0.1, remaining_deadline_seconds - (time.monotonic() - started))
                if remaining_deadline_seconds is not None
                else None
            )
            response = (
                self._proxy.fetch(request, timeout_seconds=remaining)
                if remaining_deadline_seconds is not None
                else self._proxy.fetch(request)
            )
        except (CrawlPolicyError, CrawlProxyError, OSError, ValueError, IndexError):
            return None
        if response.status_code >= 400 or not response.body:
            return None
        excerpt = html_to_excerpt(response.body)
        return excerpt or None
