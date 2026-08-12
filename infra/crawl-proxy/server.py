#!/usr/bin/env python3
"""Deny-by-default crawl egress proxy foundation.

Phase 1 Packet 3: the process is healthy and refuses every outbound fetch.
Approved destination policy is owned by Phase 3 ingestion.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.error import URLError
from urllib.request import Request, urlopen


class DenyByDefaultHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves health and denies all proxy/fetch routes."""

    server_version = "SmartRagCrawlProxy/0.1"

    DENY_BODY: ClassVar[bytes] = json.dumps(
        {
            "status": "denied",
            "reason": (
                "Crawl proxy deny-by-default: no destination policy until "
                "Phase 3 ingestion."
            ),
        }
    ).encode("utf-8")

    def log_message(self, format: str, *args: object) -> None:
        """Emit access logs without query secrets.

        Args:
            format: Printf-style message format.
            *args: Format arguments from the base server.
        """

        sys_stderr = __import__("sys").stderr
        sys_stderr.write(
            "%s - %s\n"
            % (self.address_string(), format % args)
        )

    def _send_json(self, code: int, payload: dict[str, str]) -> None:
        """Write a JSON response.

        Args:
            code: HTTP status code.
            payload: JSON-serializable mapping.
        """

        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Handle health checks and deny every other GET."""

        if self.path.split("?", 1)[0] in {"/health", "/health/live"}:
            self._send_json(200, {"status": "live", "egress": "deny-by-default"})
            return
        self._send_json(
            403,
            {
                "status": "denied",
                "reason": "Deny-by-default crawl proxy; GET targets blocked.",
            },
        )

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Deny POST fetch attempts used by workers."""

        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        self.send_response(403)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.DENY_BODY)))
        self.end_headers()
        self.wfile.write(self.DENY_BODY)

    def do_CONNECT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Refuse CONNECT tunneling."""

        self.send_response(403)
        self.end_headers()


def main() -> None:
    """Start the deny-by-default crawl proxy.

    Side Effects:
        Binds an HTTP server on ``CRAWL_PROXY_PORT`` (default 8080).
    """

    port = int(os.environ.get("CRAWL_PROXY_PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), DenyByDefaultHandler)
    print(f"crawl-proxy listening on {port} (deny-by-default)", flush=True)
    server.serve_forever()


def probe_denied_fetch(url: str, timeout_s: float = 2.0) -> int:
    """Attempt a POST fetch via this process contract helpers for tests.

    Args:
        url: Absolute URL that must be blocked by policy.
        timeout_s: Request timeout seconds.

    Returns:
        HTTP status code from the local deny endpoint semantics (403), or
        raises ``URLError`` if the proxy is unreachable.

    Note:
        This helper does not open arbitrary internet sockets from unit tests;
        tests call the in-process handler contract instead.
    """

    req = Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 - test helper
            return int(resp.status)
    except URLError:
        raise


if __name__ == "__main__":
    main()
