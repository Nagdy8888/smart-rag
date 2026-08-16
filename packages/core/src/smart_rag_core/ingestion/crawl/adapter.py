"""Approved bounded website crawl orchestration through the crawl proxy."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from uuid import UUID, uuid4

from smart_rag_core.gateways.crawl_proxy import CrawlProxyGateway, ProxyFetchRequest
from smart_rag_core.gateways.storage import StorageGateway
from smart_rag_core.ingestion.crawl.dns import DnsResolution, resolve_hostname
from smart_rag_core.ingestion.crawl.exceptions import (
    CrawlLimitExceeded,
    CrawlPolicyError,
    CrawlProxyError,
)
from smart_rag_core.ingestion.crawl.ip import parse_ip_literal
from smart_rag_core.ingestion.crawl.limits import (
    CRAWL_MAX_DECODED_BYTES_TOTAL,
    CRAWL_MAX_REDIRECTS,
    CRAWL_MAX_WIRE_BYTES_TOTAL,
    CRAWL_POLICY_VERSION,
    CRAWL_ROBOTS_MAX_BYTES,
    CRAWL_TOTAL_TIMEOUT_SECONDS,
    WEB_SNAPSHOTS_BUCKET,
)
from smart_rag_core.ingestion.crawl.policy import (
    ApprovedCrawlScope,
    NormalizedUrl,
    assert_in_scope,
    content_type_allowed,
    normalize_url,
    resolve_redirect,
)
from smart_rag_core.ingestion.crawl.robots import (
    RobotsDecision,
    evaluate_robots,
    require_robots_allowed,
    robots_url_for,
)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class CrawlFetchProvenance:
    """Append-only provenance for one fetch hop."""

    requested_url: str
    final_url: str
    status_code: int | None
    decision: str
    reason: str
    peer_ip: str | None
    pinned_ips: tuple[str, ...]
    redirect_hop: int
    wire_bytes: int
    decoded_bytes: int
    content_type: str | None
    robots: RobotsDecision | None


@dataclass(frozen=True, slots=True)
class WebSnapshotRecord:
    """Immutable stored page snapshot metadata."""

    snapshot_id: UUID
    canonical_url: str
    title: str | None
    content_type: str | None
    content_hash: str
    storage_bucket: str
    storage_path: str
    wire_bytes: int
    decoded_bytes: int
    redirect_chain: tuple[str, ...]
    peer_ip: str
    pinned_ips: tuple[str, ...]


@dataclass
class CrawlRunResult:
    """Completed crawl output for persistence layers."""

    crawl_version: int
    policy_version: str
    start_url: str
    pages_fetched: int
    wire_bytes_total: int
    decoded_bytes_total: int
    snapshots: list[WebSnapshotRecord] = field(default_factory=list[WebSnapshotRecord])
    fetch_events: list[CrawlFetchProvenance] = field(
        default_factory=list[CrawlFetchProvenance]
    )
    failure_reason: str | None = None


class _LinkExtractor(HTMLParser):
    """Collect same-document anchor href values."""

    def __init__(self) -> None:
        """Initialize href accumulator."""

        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Capture anchor href attributes."""

        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.links.append(value)


class BoundedCrawlAdapter:
    """Execute approved crawls exclusively through ``CrawlProxyGateway``."""

    def __init__(
        self,
        *,
        proxy: CrawlProxyGateway,
        storage: StorageGateway | None = None,
    ) -> None:
        """Wire proxy and optional Storage gateway for snapshot persistence."""

        self._proxy = proxy
        self._storage = storage

    def crawl(
        self,
        scope: ApprovedCrawlScope,
        *,
        source_id: UUID,
        crawl_version: int,
        max_depth: int | None = None,
        max_pages: int | None = None,
    ) -> CrawlRunResult:
        """Crawl an approved start URL with redirect revalidation and bounds.

        Args:
            scope: Approved domain/start URL boundary.
            source_id: ``document_sources.id`` for Storage paths.
            crawl_version: Monotonic crawl version integer.
            max_depth: Optional depth override bounded by approval.
            max_pages: Optional page override bounded by approval.

        Returns:
            Snapshots and provenance for persisted crawl run rows.

        Raises:
            CrawlPolicyError: When policy denies the crawl.
            CrawlProxyError: When proxy transport fails.
        """

        depth_limit = min(max_depth or scope.max_depth, scope.max_depth)
        page_limit = min(max_pages or scope.max_pages, scope.max_pages)
        start = normalize_url(scope.start_url)
        assert_in_scope(start, scope)
        started = time.monotonic()
        result = CrawlRunResult(
            crawl_version=crawl_version,
            policy_version=scope.policy_version or CRAWL_POLICY_VERSION,
            start_url=start.normalized,
            pages_fetched=0,
            wire_bytes_total=0,
            decoded_bytes_total=0,
        )
        robots_cache: dict[str, RobotsDecision] = {}
        visited: set[str] = set()
        queue: list[tuple[NormalizedUrl, int]] = [(start, 0)]

        while queue and result.pages_fetched < page_limit:
            if time.monotonic() - started > CRAWL_TOTAL_TIMEOUT_SECONDS:
                raise CrawlLimitExceeded("crawl_total_timeout_exceeded")
            current, depth = queue.pop(0)
            if current.normalized in visited:
                continue
            visited.add(current.normalized)
            try:
                assert_in_scope(current, scope)
                robots = self._robots_for(current, robots_cache)
                require_robots_allowed(robots)
                page = self._fetch_page(current, redirect_hop=0)
            except CrawlPolicyError as exc:
                result.fetch_events.append(
                    CrawlFetchProvenance(
                        requested_url=current.normalized,
                        final_url=current.normalized,
                        status_code=None,
                        decision="denied",
                        reason=exc.reason,
                        peer_ip=None,
                        pinned_ips=(),
                        redirect_hop=0,
                        wire_bytes=0,
                        decoded_bytes=0,
                        content_type=None,
                        robots=robots_cache.get(current.host),
                    )
                )
                if current.normalized == start.normalized:
                    result.failure_reason = exc.reason
                    return result
                continue
            except CrawlProxyError as exc:
                result.failure_reason = str(exc)
                return result

            result.fetch_events.append(page.provenance)
            result.wire_bytes_total += page.provenance.wire_bytes
            result.decoded_bytes_total += page.provenance.decoded_bytes
            if result.wire_bytes_total > CRAWL_MAX_WIRE_BYTES_TOTAL:
                raise CrawlLimitExceeded("crawl_wire_bytes_total_exceeded")
            if result.decoded_bytes_total > CRAWL_MAX_DECODED_BYTES_TOTAL:
                raise CrawlLimitExceeded("crawl_decoded_bytes_total_exceeded")

            if not content_type_allowed(page.provenance.content_type):
                if current.normalized == start.normalized:
                    result.failure_reason = "unsupported_content_type"
                    return result
                continue

            snapshot = self._persist_snapshot(
                source_id=source_id,
                crawl_version=crawl_version,
                page=page,
            )
            result.snapshots.append(snapshot)
            result.pages_fetched += 1

            if depth >= depth_limit:
                continue
            from urllib.parse import urljoin

            for link in extract_links(page.body.decode("utf-8", errors="replace")):
                try:
                    linked = normalize_url(urljoin(current.normalized, link))
                    assert_in_scope(linked, scope)
                    if linked.normalized not in visited:
                        queue.append((linked, depth + 1))
                except CrawlPolicyError:
                    continue

        return result

    def _robots_for(
        self,
        origin: NormalizedUrl,
        cache: dict[str, RobotsDecision],
    ) -> RobotsDecision:
        """Fetch and cache robots.txt for an origin host."""

        if origin.host in cache:
            return cache[origin.host]
        robots_url = robots_url_for(origin)
        robots_page = self._fetch_page(normalize_url(robots_url), redirect_hop=0)
        body = robots_page.body.decode("utf-8", errors="replace")
        if len(body) > CRAWL_ROBOTS_MAX_BYTES:
            raise CrawlPolicyError("robots_oversize", code="robots_denied")
        decision = evaluate_robots(body, robots_url, origin)
        cache[origin.host] = decision
        return decision

    def _fetch_page(
        self,
        url: NormalizedUrl,
        *,
        redirect_hop: int,
    ) -> _FetchedPage:
        """Fetch one URL through the proxy with manual redirect handling."""

        chain: list[str] = [url.normalized]
        current = url
        for hop in range(CRAWL_MAX_REDIRECTS + 1):
            dns = self._resolve(current)
            if current.host != dns.hostname and parse_ip_literal(current.host) is None:
                dns = resolve_hostname(current.host)
            pin_ip = dns.pinned_ips[0]
            response = self._proxy.fetch(
                ProxyFetchRequest(
                    url=current.normalized,
                    method="GET",
                    host_header=current.host,
                    pin_ip=pin_ip,
                    port=current.port,
                    use_tls=current.scheme == "https",
                    headers={"Accept": "text/html,text/plain,application/xhtml+xml"},
                )
            )
            if pin_ip != response.peer_ip:
                raise CrawlPolicyError("peer_ip_mismatch", code="peer_mismatch")
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location") or response.headers.get(
                    "location"
                )
                if not location:
                    raise CrawlPolicyError("redirect_missing_location", code="redirect")
                current = resolve_redirect(
                    current,
                    location,
                    hop=hop + 1,
                    max_redirects=CRAWL_MAX_REDIRECTS,
                )
                chain.append(current.normalized)
                continue
            provenance = CrawlFetchProvenance(
                requested_url=url.normalized,
                final_url=current.normalized,
                status_code=response.status_code,
                decision="allowed" if response.status_code < 400 else "failed",
                reason="ok"
                if response.status_code < 400
                else f"http_{response.status_code}",
                peer_ip=response.peer_ip,
                pinned_ips=dns.pinned_ips,
                redirect_hop=redirect_hop + hop,
                wire_bytes=response.wire_bytes,
                decoded_bytes=response.decoded_bytes,
                content_type=response.content_type,
                robots=None,
            )
            title = extract_title(response.body)
            return _FetchedPage(
                url=current,
                body=response.body,
                title=title,
                provenance=provenance,
                redirect_chain=tuple(chain),
            )
        raise CrawlPolicyError("redirect_limit_exceeded", code="limit_exceeded")

    def _resolve(self, url: NormalizedUrl) -> DnsResolution:
        """Resolve or classify literal hosts."""

        literal = parse_ip_literal(url.host)
        if literal is not None:
            from smart_rag_core.ingestion.crawl.ip import validate_resolved_addresses

            pinned = validate_resolved_addresses([literal])
            return DnsResolution(hostname=url.host, pinned_ips=tuple(pinned))
        return resolve_hostname(url.host)

    def _persist_snapshot(
        self,
        *,
        source_id: UUID,
        crawl_version: int,
        page: _FetchedPage,
    ) -> WebSnapshotRecord:
        """Upload snapshot bytes to ``web-snapshots`` when Storage is configured."""

        content_hash = hashlib.sha256(page.body).hexdigest()
        safe_name = _safe_snapshot_name(page.url)
        storage_path = f"sources/{source_id}/crawls/{crawl_version}/{safe_name}.html"
        if self._storage is not None:
            self._storage.upload_object(
                bucket=WEB_SNAPSHOTS_BUCKET,
                object_path=storage_path,
                data=page.body,
                content_type=page.provenance.content_type or "text/html",
            )
        return WebSnapshotRecord(
            snapshot_id=uuid4(),
            canonical_url=page.url.normalized,
            title=page.title,
            content_type=page.provenance.content_type,
            content_hash=content_hash,
            storage_bucket=WEB_SNAPSHOTS_BUCKET,
            storage_path=storage_path,
            wire_bytes=page.provenance.wire_bytes,
            decoded_bytes=page.provenance.decoded_bytes,
            redirect_chain=page.redirect_chain,
            peer_ip=page.provenance.peer_ip or "",
            pinned_ips=page.provenance.pinned_ips,
        )


@dataclass(frozen=True, slots=True)
class _FetchedPage:
    """Internal fetched page with provenance."""

    url: NormalizedUrl
    body: bytes
    title: str | None
    provenance: CrawlFetchProvenance
    redirect_chain: tuple[str, ...]


def extract_links(html: str) -> list[str]:
    """Extract anchor href links from HTML."""

    parser = _LinkExtractor()
    parser.feed(html)
    return parser.links


def extract_title(body: bytes) -> str | None:
    """Extract a document title when present."""

    text = body.decode("utf-8", errors="replace")
    match = _TITLE_RE.search(text)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()[:512] or None


def _safe_snapshot_name(url: NormalizedUrl) -> str:
    """Derive a filesystem-safe snapshot filename stem."""

    digest = hashlib.sha256(url.normalized.encode("utf-8")).hexdigest()[:16]
    return digest
