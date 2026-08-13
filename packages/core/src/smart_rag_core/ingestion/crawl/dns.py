"""Blocking DNS resolution for crawl SSRF checks."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass

from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError
from smart_rag_core.ingestion.crawl.ip import validate_resolved_addresses
from smart_rag_core.ingestion.crawl.limits import CRAWL_DNS_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class DnsResolution:
    """Approved DNS answers for one hostname."""

    hostname: str
    pinned_ips: tuple[str, ...]


def resolve_hostname(
    hostname: str, *, timeout_seconds: float | None = None
) -> DnsResolution:
    """Resolve all A/AAAA answers and reject mixed safe/unsafe sets.

    Args:
        hostname: Hostname to resolve (not an IP literal).
        timeout_seconds: Optional resolver timeout override.

    Returns:
        Approved IP list for proxy pinning.

    Raises:
        CrawlPolicyError: On resolution failure or blocked answers.
    """

    timeout = (
        timeout_seconds if timeout_seconds is not None else CRAWL_DNS_TIMEOUT_SECONDS
    )
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        infos = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise CrawlPolicyError("dns_resolution_failed", code="dns_failure") from exc
    finally:
        socket.setdefaulttimeout(previous)

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_text = sockaddr[0]
        try:
            addresses.append(ipaddress.ip_address(ip_text))
        except ValueError as exc:
            raise CrawlPolicyError("dns_invalid_answer", code="dns_failure") from exc
    pinned = validate_resolved_addresses(addresses)
    return DnsResolution(hostname=hostname, pinned_ips=tuple(pinned))
