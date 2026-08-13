"""IP literal parsing and SSRF block classification."""

from __future__ import annotations

import ipaddress
import re
from typing import Final

from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError

_METADATA_IPV4: Final = ipaddress.ip_address("169.254.169.254")
_DECIMAL_IPV4_RE: Final = re.compile(r"^\d+$")
_OCTAL_IPV4_RE: Final = re.compile(r"^(?:0[0-7]{1,3}\.){3}0[0-7]{1,3}$")
_HEX_IPV4_RE: Final = re.compile(r"^(?:0x[0-9a-fA-F]{1,2}\.){3}0x[0-9a-fA-F]{1,2}$")


def strip_ipv6_zone(host: str) -> str:
    """Remove an IPv6 zone identifier suffix when present.

    Args:
        host: Hostname or bracketed IPv6 literal.

    Returns:
        Host without ``%zone`` suffix.

    Raises:
        CrawlPolicyError: When a zone id is present (always rejected).
    """

    if "%" in host:
        raise CrawlPolicyError("ipv6_zone_id_forbidden", code="ipv6_zone")
    return host.strip("[]")


def parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse dotted, decimal, octal, hex, and mapped IPv6 host literals.

    Args:
        host: Raw host component from a URL.

    Returns:
        Parsed address when the host is an IP literal; otherwise ``None``.

    Raises:
        CrawlPolicyError: On ambiguous, malformed, or non-canonical literals.
    """

    candidate = strip_ipv6_zone(host)
    if _DECIMAL_IPV4_RE.fullmatch(candidate):
        value = int(candidate)
        if value < 0 or value > 0xFFFFFFFF:
            raise CrawlPolicyError("decimal_ipv4_out_of_range", code="invalid_ip")
        return ipaddress.IPv4Address(value)
    if "." in candidate and _has_non_canonical_ipv4_octet(candidate):
        raise CrawlPolicyError("non_decimal_ip_encoding_forbidden", code="invalid_ip")
    if _OCTAL_IPV4_RE.fullmatch(candidate) or _HEX_IPV4_RE.fullmatch(candidate):
        raise CrawlPolicyError("non_decimal_ip_encoding_forbidden", code="invalid_ip")
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def classify_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Reject private, loopback, link-local, metadata, and reserved targets.

    Args:
        address: Resolved or literal IP address.

    Raises:
        CrawlPolicyError: When the address is not a safe public target.
    """

    if address.is_loopback:
        raise CrawlPolicyError("loopback_ip_forbidden", code="loopback")
    if address.is_unspecified:
        raise CrawlPolicyError("unspecified_ip_forbidden", code="unspecified")
    if isinstance(address, ipaddress.IPv4Address) and address == _METADATA_IPV4:
        raise CrawlPolicyError("metadata_ip_forbidden", code="metadata")
    if address.is_link_local:
        raise CrawlPolicyError("link_local_ip_forbidden", code="link_local")
    if address.is_private:
        raise CrawlPolicyError("private_ip_forbidden", code="private_ip")
    if address.is_multicast:
        raise CrawlPolicyError("multicast_ip_forbidden", code="multicast")
    if address.is_reserved:
        raise CrawlPolicyError("reserved_ip_forbidden", code="reserved")
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped
        if mapped is not None:
            classify_ip(mapped)
    if isinstance(address, ipaddress.IPv4Address) and address in ipaddress.IPv4Network(
        "100.64.0.0/10"
    ):
        raise CrawlPolicyError("cg_nat_ip_forbidden", code="private_ip")


def validate_resolved_addresses(
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address],
) -> list[str]:
    """Validate every DNS answer and return canonical string forms.

    Args:
        addresses: All A/AAAA records for one resolution.

    Returns:
        Sorted unique string IP forms approved for pinning.

    Raises:
        CrawlPolicyError: When no answers exist or any answer is blocked.
    """

    if not addresses:
        raise CrawlPolicyError("dns_no_answers", code="dns_failure")
    approved: list[str] = []
    for address in addresses:
        classify_ip(address)
        approved.append(str(address))
    return sorted(set(approved))


def _has_non_canonical_ipv4_octet(host: str) -> bool:
    """Return whether any dotted IPv4 octet uses hex/octal encoding."""

    parts = host.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if part.startswith("0") and len(part) > 1 and part.isdigit():
            return True
        if part.lower().startswith("0x"):
            return True
    return False
