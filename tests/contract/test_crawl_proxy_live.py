"""Live crawl-proxy contract tests against the Packet 8 localhost overlay."""

from __future__ import annotations

import httpx
import pytest
from smart_rag_core.gateways.crawl_proxy import CrawlProxyGateway, ProxyFetchRequest
from smart_rag_core.ingestion.crawl.exceptions import CrawlProxyError

from tests.contract.integration_support import (
    packet8_crawl_proxy_url,
    read_process_env,
)


def _require_live_proxy() -> str:
    """Return the overlay proxy URL or skip/fail based on the integration gate."""

    base = packet8_crawl_proxy_url()
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{base}/health")
    except httpx.HTTPError:
        if read_process_env("SMART_RAG_REQUIRE_CRAWL_PROXY") == "1":
            pytest.fail(
                f"SMART_RAG_REQUIRE_CRAWL_PROXY=1 but proxy unreachable at {base}"
            )
        pytest.skip(f"crawl-proxy overlay unreachable at {base}")
    if response.status_code != 200:
        if read_process_env("SMART_RAG_REQUIRE_CRAWL_PROXY") == "1":
            pytest.fail(f"crawl-proxy health returned {response.status_code}")
        pytest.skip(f"crawl-proxy health returned {response.status_code}")
    return base


def test_live_compose_proxy_health() -> None:
    """Published Packet 8 crawl-proxy answers a live health check."""

    base = _require_live_proxy()
    with httpx.Client(timeout=3.0) as client:
        payload = client.get(f"{base}/health").json()
    assert payload["status"] == "live"


def test_live_compose_proxy_unpinned_fetch_fails_closed() -> None:
    """Live proxy rejects fetches that omit the required pin contract."""

    base = _require_live_proxy()
    with httpx.Client(timeout=5.0) as client:
        response = client.post(f"{base}/fetch", json={"url": "http://example.com/"})
    assert response.status_code in {400, 403}
    body = response.json()
    assert "error" in body or body.get("status") == "denied"


def test_live_compose_proxy_peer_mismatch_or_unroutable_fails_closed() -> None:
    """Live execute_fetch fails closed when the pin cannot be a matching peer.

    TEST-NET-1 ``192.0.2.1`` is documentation-only and must not complete a
    successful fetch through the restricted proxy.
    """

    base = _require_live_proxy()
    gateway = CrawlProxyGateway(proxy_base_url=base, timeout_seconds=8.0)
    with pytest.raises(CrawlProxyError):
        gateway.fetch(
            ProxyFetchRequest(
                url="http://example.com/",
                method="GET",
                host_header="example.com",
                pin_ip="192.0.2.1",
                port=80,
                use_tls=False,
                headers={},
                connect_timeout_s=2.0,
                read_timeout_s=2.0,
            )
        )
