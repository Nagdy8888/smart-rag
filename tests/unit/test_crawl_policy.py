"""Unit tests for crawl URL and IP SSRF policy."""

from __future__ import annotations

import ipaddress
import socket
from unittest.mock import MagicMock, patch

import pytest
from smart_rag_core.ingestion.crawl.dns import resolve_hostname
from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError
from smart_rag_core.ingestion.crawl.ip import (
    classify_ip,
    parse_ip_literal,
    validate_resolved_addresses,
)
from smart_rag_core.ingestion.crawl.policy import (
    ApprovedCrawlScope,
    assert_in_scope,
    normalize_url,
    resolve_redirect,
)


def _scope(domain: str = "example.com") -> ApprovedCrawlScope:
    """Build one approved crawl scope for policy unit tests.

    Args:
        domain: Approved hostname used as start URL and allowlist.

    Returns:
        Frozen ``ApprovedCrawlScope`` with small depth/page caps.
    """

    return ApprovedCrawlScope(
        approval_id="a1",
        source_id="s1",
        start_url=f"https://{domain}/",
        approved_domain=domain,
        policy_version="crawl_v1",
        max_depth=2,
        max_pages=10,
        requester_user_id=None,
        reviewer_user_id=None,
    )


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://127.0.0.1/", "loopback"),
        ("http://localhost/", "invalid_host"),
        ("http://[::1]/", "loopback"),
        ("http://169.254.169.254/", "metadata"),
        ("http://10.0.0.1/", "private_ip"),
        ("http://192.168.0.1/", "private_ip"),
        ("http://100.64.0.1/", "private_ip"),
        ("http://2130706433/", "loopback"),
        ("http://0177.0.0.1/", "invalid_ip"),
        ("http://0x7f.0.0.1/", "invalid_ip"),
        ("http://127.1/", "invalid_host"),
        ("ftp://example.com/", "invalid_url"),
        ("http://user:pass@example.com/", "userinfo"),
        ("http://example.com:8080/", "invalid_url"),
        ("http://example.com/path#frag", "invalid_url"),
    ],
)
def test_normalize_url_ssrf_vectors_fail_closed(url: str, code: str) -> None:
    """Localhost/private/metadata and malformed URLs fail closed."""

    with pytest.raises(CrawlPolicyError):
        normalize_url(url)


def test_ipv6_mapped_private_rejected() -> None:
    """IPv4-mapped private IPv6 literals are blocked."""

    with pytest.raises(CrawlPolicyError):
        classify_ip(ipaddress.ip_address("::ffff:127.0.0.1"))


def test_mixed_dns_answers_fail_closed() -> None:
    """Mixed safe/public and unsafe DNS answers fail closed."""

    public = ipaddress.ip_address("93.184.216.34")
    private = ipaddress.ip_address("10.0.0.1")
    with pytest.raises(CrawlPolicyError):
        validate_resolved_addresses([public, private])


def test_redirect_loop_detected() -> None:
    """Self redirect loops fail closed."""

    current = normalize_url("https://example.com/a")
    with pytest.raises(CrawlPolicyError) as exc:
        resolve_redirect(current, "/a", hop=1, max_redirects=5)
    assert exc.value.code == "redirect_loop"


def test_scope_violation_for_unapproved_subdomain() -> None:
    """Hosts outside approved domain are rejected."""

    url = normalize_url("https://evil.example.org/page")
    with pytest.raises(CrawlPolicyError) as exc:
        assert_in_scope(url, _scope("example.com"))
    assert exc.value.code == "scope_violation"


def test_idna_confusion_rejected() -> None:
    """Malformed IDNA host labels fail closed."""

    with pytest.raises(CrawlPolicyError):
        normalize_url("http://xn--bad.invalid./")


@patch("smart_rag_core.ingestion.crawl.dns.socket.getaddrinfo")
def test_dns_rebinding_pin_list(mock_getaddrinfo: MagicMock) -> None:
    """DNS resolution returns pinned public IPs only."""

    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
    ]
    resolution = resolve_hostname("example.com")
    assert resolution.pinned_ips == ("93.184.216.34",)


def test_decimal_ip_maps_to_loopback() -> None:
    """Decimal IPv4 literals are parsed and classified."""

    parsed = parse_ip_literal("2130706433")
    assert parsed is not None
    with pytest.raises(CrawlPolicyError):
        classify_ip(parsed)
