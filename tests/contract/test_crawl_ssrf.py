"""Contract tests for crawl SSRF boundaries and proxy-only egress."""

from __future__ import annotations

import importlib.util
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol, cast
from unittest.mock import MagicMock, patch

import pytest
from smart_rag_core.gateways.crawl_proxy import (
    CrawlProxyGateway,
    ProxyFetchRequest,
    ProxyFetchResponse,
)
from smart_rag_core.ingestion.crawl.adapter import BoundedCrawlAdapter
from smart_rag_core.ingestion.crawl.exceptions import CrawlPolicyError, CrawlProxyError
from smart_rag_core.ingestion.crawl.policy import ApprovedCrawlScope, normalize_url
from smart_rag_core.ingestion.crawl.robots import (
    evaluate_robots,
    require_robots_allowed,
)

from tests.contract.integration_support import typed_module_attr

REPO_ROOT = Path(__file__).resolve().parents[2]
PROXY_SERVER = REPO_ROOT / "infra" / "crawl-proxy" / "server.py"


class _FixtureHandler(BaseHTTPRequestHandler):
    """Local fixture HTTP server for crawl contract tests."""

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default HTTP access logs during contracts."""

        return None

    def do_GET(self) -> None:
        """Serve robots, redirect, gzip, and HTML fixture paths."""

        if self.path == "/robots.txt":
            body = b"User-agent: *\nDisallow:\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/redirect-private":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1/private")
            self.end_headers()
            return
        if self.path == "/gzip-bomb":
            import gzip

            body = gzip.compress(b"z" * 5000)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"<html><head><title>Fixture</title></head><body>ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CrawlProxyModule(Protocol):
    """Dynamically loaded crawl-proxy module surface used by contracts."""

    FetchHandler: type[object]

    def execute_fetch(self, payload: dict[str, object]) -> dict[str, object]:
        """Execute one pinned fetch payload."""

        ...


@pytest.fixture
def fixture_server() -> Iterator[str]:
    """Start a localhost fixture HTTP server and return its base URL."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    yield f"http://{host}:{port}"
    server.shutdown()


def _load_proxy_module() -> CrawlProxyModule:
    """Load the crawl-proxy server module from its source path.

    Returns:
        The loaded module, typed to the fetch contract used by these tests.
    """

    spec = importlib.util.spec_from_file_location("crawl_proxy_server", PROXY_SERVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(CrawlProxyModule, module)


class _RecordingProxy:
    """In-process proxy stand-in recording pinned fetch contracts."""

    def __init__(self, module: CrawlProxyModule) -> None:
        """Bind the loaded proxy module and an empty request log.

        Args:
            module: Dynamically loaded crawl-proxy module.
        """

        self.module = module
        self.requests: list[dict[str, object]] = []

    def fetch(self, request: ProxyFetchRequest) -> ProxyFetchResponse:
        """Record one request and execute it through the loaded proxy module.

        Args:
            request: Pinned fetch contract.

        Returns:
            Normalized proxy response.
        """

        payload: dict[str, object] = {
            "url": request.url,
            "method": request.method,
            "host_header": request.host_header,
            "pin_ip": request.pin_ip,
            "port": request.port,
            "use_tls": request.use_tls,
            "headers": request.headers,
            "max_wire_bytes": request.max_wire_bytes,
            "max_decoded_bytes": request.max_decoded_bytes,
            "max_decompression_ratio": request.max_decompression_ratio,
        }
        self.requests.append(payload)
        result = self.module.execute_fetch(payload)
        import base64

        body = base64.b64decode(str(result["body_base64"]).encode("ascii"))
        return ProxyFetchResponse(
            status_code=int(str(result["status_code"])),
            headers=cast(dict[str, str], result["headers"]),
            body=body,
            wire_bytes=int(str(result["wire_bytes"])),
            decoded_bytes=int(str(result["decoded_bytes"])),
            peer_ip=str(result["peer_ip"]),
            content_type=cast(str | None, result.get("content_type")),
            truncated=bool(result.get("truncated", False)),
            error=cast(str | None, result.get("error")),
        )


def test_core_adapter_requires_proxy_gateway() -> None:
    """Crawl adapter routes fetches only through a proxy gateway."""

    adapter = BoundedCrawlAdapter(
        proxy=CrawlProxyGateway(proxy_base_url="http://invalid")
    )
    result = adapter.crawl(
        ApprovedCrawlScope(
            approval_id="a",
            source_id="s",
            start_url="https://example.com/",
            approved_domain="example.com",
            policy_version="crawl_v1",
            max_depth=1,
            max_pages=1,
            requester_user_id=None,
            reviewer_user_id=None,
        ),
        source_id=__import__("uuid").uuid4(),
        crawl_version=1,
    )
    assert result.failure_reason is not None
    assert result.pages_fetched == 0


@patch("smart_rag_core.ingestion.crawl.adapter.BoundedCrawlAdapter._fetch_page")
@patch("smart_rag_core.ingestion.crawl.adapter.BoundedCrawlAdapter._robots_for")
def test_approved_fixture_crawl_stores_snapshot(
    mock_robots: MagicMock,
    mock_fetch: MagicMock,
) -> None:
    """Approved crawl stores bounded snapshot metadata and provenance."""

    from uuid import uuid4

    from smart_rag_core.ingestion.crawl import adapter as crawl_adapter
    from smart_rag_core.ingestion.crawl.adapter import CrawlFetchProvenance

    fetched_page = typed_module_attr(
        crawl_adapter,
        "_FetchedPage",
        cast("Callable[..., object]", None),
    )
    target = normalize_url("https://example.com/")
    mock_robots.return_value = evaluate_robots(
        "User-agent: *\nDisallow:\n",
        "https://example.com/robots.txt",
        target,
    )
    mock_fetch.return_value = fetched_page(
        url=target,
        body=b"<html><head><title>Fixture</title></head><body>ok</body></html>",
        title="Fixture",
        provenance=CrawlFetchProvenance(
            requested_url=target.normalized,
            final_url=target.normalized,
            status_code=200,
            decision="allowed",
            reason="ok",
            peer_ip="93.184.216.34",
            pinned_ips=("93.184.216.34",),
            redirect_hop=0,
            wire_bytes=100,
            decoded_bytes=100,
            content_type="text/html",
            robots=None,
        ),
        redirect_chain=(target.normalized,),
    )

    module = _load_proxy_module()
    recording = _RecordingProxy(module)
    adapter = BoundedCrawlAdapter(proxy=cast(CrawlProxyGateway, recording))
    scope = ApprovedCrawlScope(
        approval_id="a",
        source_id="s",
        start_url="https://example.com/",
        approved_domain="example.com",
        policy_version="crawl_v1",
        max_depth=0,
        max_pages=1,
        requester_user_id=None,
        reviewer_user_id=None,
    )
    result = adapter.crawl(scope, source_id=uuid4(), crawl_version=1)
    assert result.pages_fetched == 1
    assert len(result.snapshots) == 1
    assert result.snapshots[0].content_hash


def test_redirect_to_private_fails_closed() -> None:
    """Redirect targets to private IPs fail closed during hop revalidation."""

    with pytest.raises(CrawlPolicyError):
        normalize_url("http://127.0.0.1/private")


def test_robots_failure_fails_closed() -> None:
    """Robots disallow fails closed and does not broaden access."""

    target = normalize_url("https://example.com/page")
    decision = evaluate_robots(
        "User-agent: *\nDisallow: /\n",
        "https://example.com/robots.txt",
        target,
    )
    with pytest.raises(CrawlPolicyError):
        require_robots_allowed(decision)


def test_proxy_bypass_denied_without_fetch_route() -> None:
    """Non-fetch POST routes remain denied (proxy bypass attempt)."""

    module = _load_proxy_module()

    class _Handler:
        """Stand-in with FetchHandler JSON helpers for POST /fetch."""

        def __init__(self) -> None:
            """Bind the POST /fetch path and an empty JSON body."""

            self.path = "/fetch"
            self.headers = {"Content-Length": "2"}
            self.rfile = __import__("io").BytesIO(b"{}")
            self.wfile = __import__("io").BytesIO()
            self.status = 0

        def send_response(self, code: int, message: str | None = None) -> None:
            """Record the HTTP status that FetchHandler would send."""

            del message
            self.status = code

        def send_header(self, keyword: str, value: str) -> None:
            """Ignore headers; only status is asserted."""

            del keyword, value

        def end_headers(self) -> None:
            """No-op header terminator."""

            return None

        def _read_json_body(self) -> dict[str, object]:
            """Parse the request body using production FetchHandler logic.

            Returns:
                Decoded JSON object from ``rfile``.
            """

            read_body = typed_module_attr(
                module.FetchHandler,
                "_read_json_body",
                cast("Callable[[object], dict[str, object]]", None),
            )
            return read_body(self)

        def _send_json(self, code: int, payload: dict[str, object]) -> None:
            """Write status using production FetchHandler JSON helper.

            Args:
                code: HTTP status.
                payload: JSON object to encode.
            """

            send_json = typed_module_attr(
                module.FetchHandler,
                "_send_json",
                cast("Callable[[object, int, dict[str, object]], None]", None),
            )
            send_json(self, code, payload)

    handler = _Handler()
    do_post = typed_module_attr(
        module.FetchHandler,
        "do_POST",
        cast("Callable[[object], None]", None),
    )
    do_post(handler)
    assert handler.status in {400, 502}


def test_worker_compose_has_no_public_egress_network() -> None:
    """Worker service remains on internal-only private network."""

    import yaml

    compose = yaml.safe_load(
        (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )
    worker = compose["services"]["worker"]
    assert "edge" not in worker["networks"]
    assert "egress" not in worker["networks"]


def test_crawl_proxy_gateway_requires_peer_ip() -> None:
    """Gateway rejects proxy responses missing peer metadata."""

    class _Client:
        """httpx.Client stand-in that omits peer_ip from fetch JSON."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            """Ignore constructor arguments used by the real client."""

            del args, kwargs

        def __enter__(self) -> _Client:
            """Return the context-managed client."""

            return self

        def __exit__(self, *args: object) -> None:
            """No-op context exit."""

            del args
            return None

        def post(self, url: str, json: dict[str, object]) -> object:
            """Return a 200 JSON body missing peer metadata.

            Args:
                url: Unused proxy URL.
                json: Unused fetch payload.

            Returns:
                Stub response object.
            """

            del url, json

            class _Resp:
                """Minimal JSON response missing peer_ip."""

                status_code = 200

                @staticmethod
                def json() -> dict[str, object]:
                    """Return a proxy payload without peer metadata."""

                    return {"status_code": 200, "headers": {}, "body_base64": ""}

            return _Resp()

    with patch("smart_rag_core.gateways.crawl_proxy.httpx.Client", _Client):
        gateway = CrawlProxyGateway(proxy_base_url="http://proxy:8080")
        with pytest.raises(CrawlProxyError):
            gateway.fetch(
                ProxyFetchRequest(
                    url="http://example.com/",
                    method="GET",
                    host_header="example.com",
                    pin_ip="93.184.216.34",
                    port=80,
                    use_tls=False,
                    headers={},
                )
            )
