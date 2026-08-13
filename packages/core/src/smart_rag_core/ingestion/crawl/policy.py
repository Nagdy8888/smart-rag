"""URL normalization, scope, and hop validation for approved crawls."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError
from smart_rag_core.ingestion.crawl.ip import (
    classify_ip,
    parse_ip_literal,
    strip_ipv6_zone,
)
from smart_rag_core.ingestion.crawl.limits import (
    CRAWL_ALLOWED_PORTS,
    CRAWL_ALLOWED_SCHEMES,
    CRAWL_MAX_URL_LENGTH,
)

_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "cookie2",
        "set-cookie",
        "proxy-authorization",
        "x-api-key",
    }
)
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class NormalizedUrl:
    """Canonical HTTP(S) URL ready for DNS and scope checks."""

    original: str
    normalized: str
    scheme: str
    host: str
    port: int
    path: str
    registrable_domain: str


@dataclass(frozen=True, slots=True)
class ApprovedCrawlScope:
    """Owner/admin-approved crawl boundary."""

    approval_id: str
    source_id: str
    start_url: str
    approved_domain: str
    policy_version: str
    max_depth: int
    max_pages: int
    requester_user_id: str | None
    reviewer_user_id: str | None


def strip_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    """Remove credentials and cookies that must not cross hops.

    Args:
        headers: Request header mapping.

    Returns:
        Sanitized headers safe to forward to the crawl proxy.
    """

    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _SENSITIVE_HEADER_NAMES
    }


def normalize_url(raw_url: str) -> NormalizedUrl:
    """Normalize one HTTP(S) URL and reject SSRF-prone forms.

    Args:
        raw_url: User or redirect supplied URL.

    Returns:
        Canonical URL metadata.

    Raises:
        CrawlPolicyError: For unsupported schemes, credentials, bad hosts, or
            overlong URLs.
    """

    if not raw_url or len(raw_url) > CRAWL_MAX_URL_LENGTH:
        raise CrawlPolicyError("url_length_exceeded", code="invalid_url")
    parts = urlsplit(raw_url.strip())
    if parts.fragment:
        raise CrawlPolicyError("fragment_forbidden", code="invalid_url")
    if parts.username or parts.password:
        raise CrawlPolicyError("userinfo_forbidden", code="userinfo")
    scheme = parts.scheme.lower()
    if scheme not in CRAWL_ALLOWED_SCHEMES:
        raise CrawlPolicyError("scheme_not_allowed", code="invalid_url")
    host_raw = parts.hostname
    if not host_raw:
        raise CrawlPolicyError("missing_host", code="invalid_url")
    host = _normalize_host(host_raw)
    literal = parse_ip_literal(host)
    if literal is not None:
        classify_ip(literal)
    elif host == "localhost" or host.endswith(".localhost"):
        raise CrawlPolicyError("localhost_forbidden", code="loopback")
    port = parts.port or (443 if scheme == "https" else 80)
    if port not in CRAWL_ALLOWED_PORTS:
        raise CrawlPolicyError("port_not_allowed", code="invalid_url")
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    netloc = host if port in {80, 443} else f"{host}:{port}"
    normalized = urlunsplit((scheme, netloc, path, "", ""))
    domain = registrable_domain(host)
    literal = parse_ip_literal(host)
    if literal is not None:
        domain = host
    return NormalizedUrl(
        original=raw_url,
        normalized=normalized,
        scheme=scheme,
        host=host,
        port=port,
        path=path,
        registrable_domain=domain,
    )


def _normalize_host(host: str) -> str:
    """Normalize hostname or IP literal host component."""

    host = strip_ipv6_zone(host.strip().lower().rstrip("."))
    literal = parse_ip_literal(host)
    if literal is not None:
        return str(literal)
    if host.startswith("xn--"):
        try:
            host = host.encode("ascii").decode("idna")
        except UnicodeError as exc:
            raise CrawlPolicyError("idna_decode_failed", code="invalid_host") from exc
    if not _is_valid_hostname(host):
        raise CrawlPolicyError("invalid_hostname", code="invalid_host")
    if _looks_like_ip_hostname(host):
        raise CrawlPolicyError("ambiguous_ip_hostname", code="invalid_host")
    return host


def _looks_like_ip_hostname(host: str) -> bool:
    """Reject dotted hosts with numeric labels that are not canonical IPs."""

    labels = host.split(".")
    if not all(label.isdigit() for label in labels):
        return False
    if len(labels) == 4:
        try:
            parse_ip_literal(host)
        except CrawlPolicyError:
            return True
        return False
    return True


def _is_valid_hostname(host: str) -> bool:
    """Return whether a DNS hostname label sequence is well formed."""

    if len(host) > 253 or ".." in host:
        return False
    labels = host.split(".")
    if len(labels) < 2:
        return False
    return all(_HOST_LABEL_RE.fullmatch(label) for label in labels)


def registrable_domain(host: str) -> str:
    """Return the approved scope domain for a host (simple suffix match)."""

    host = host.lower().rstrip(".")
    return host


def assert_in_scope(url: NormalizedUrl, scope: ApprovedCrawlScope) -> None:
    """Ensure a normalized URL remains within the approved domain boundary.

    Args:
        url: Candidate hop URL.
        scope: Approved crawl scope.

    Raises:
        CrawlPolicyError: When the host is outside the approved domain.
    """

    approved = scope.approved_domain.lower().rstrip(".")
    host = url.host.lower()
    if host == approved or host.endswith(f".{approved}"):
        return
    raise CrawlPolicyError("url_outside_approved_scope", code="scope_violation")


def resolve_redirect(
    current: NormalizedUrl,
    location: str,
    *,
    hop: int,
    max_redirects: int,
) -> NormalizedUrl:
    """Resolve one redirect Location header into a revalidated URL.

    Args:
        current: Current hop URL.
        location: Raw Location header value.
        hop: Zero-based redirect hop count after this redirect.
        max_redirects: Maximum allowed redirects.

    Returns:
        Normalized redirect target.

    Raises:
        CrawlPolicyError: On redirect loops or excess hops.
    """

    if hop >= max_redirects:
        raise CrawlPolicyError("redirect_limit_exceeded", code="limit_exceeded")
    target = urljoin(current.normalized, location.strip())
    normalized = normalize_url(target)
    if normalized.normalized == current.normalized:
        raise CrawlPolicyError("redirect_loop", code="redirect_loop")
    return normalized


def content_type_allowed(content_type: str | None) -> bool:
    """Return whether a response MIME type may be snapshotted."""

    if not content_type:
        return False
    mime = content_type.split(";", 1)[0].strip().lower()
    return mime in {
        "text/html",
        "text/plain",
        "application/xhtml+xml",
    }
