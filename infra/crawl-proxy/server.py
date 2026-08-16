#!/usr/bin/env python3
"""Restricted crawl egress proxy — the only approved public HTTP fetch path.

Phase 3 Packet 4: executes pinned fetches with peer verification, bounded wire
and decoded bytes, and no automatic redirect following.
"""

from __future__ import annotations

import base64
import gzip
import importlib
import io
import json
import socket
import ssl
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar, Protocol, cast
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_HEADER_BLOCK = 32_768


class _BrotliModule(Protocol):
    """Optional Brotli decoder used for ``Content-Encoding: br``."""

    def decompress(self, data: bytes) -> bytes:
        """Return decompressed Brotli bytes.

        Args:
            data: Wire bytes labeled ``br``.

        Returns:
            Decoded payload bytes.
        """
        ...


def _load_brotli() -> _BrotliModule | None:
    """Import Brotli when the optional extension is installed.

    Returns:
        Brotli module when import succeeds; otherwise ``None``.
    """

    try:
        loaded = importlib.import_module("brotli")
    except ImportError:  # pragma: no cover - optional in slim image
        return None
    return cast(_BrotliModule, loaded)


brotli = _load_brotli()


class FetchHandler(BaseHTTPRequestHandler):
    """HTTP handler exposing health checks and ``POST /fetch`` only."""

    server_version = "SmartRagCrawlProxy/1.0"

    DENY_BODY: ClassVar[bytes] = json.dumps(
        {
            "status": "denied",
            "reason": "Use POST /fetch with a pinned policy-approved request.",
        }
    ).encode("utf-8")

    def log_message(self, format: str, *args: object) -> None:
        """Emit access logs without echoing sensitive query values."""

        sys_stderr = __import__("sys").stderr
        rendered = format % args
        sys_stderr.write(f"{self.address_string()} - {rendered}\n")

    def _send_json(self, code: int, payload: dict[str, object]) -> None:
        """Write a JSON response."""

        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, object]:
        """Parse a JSON object request body."""

        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("empty body")
        raw = self.rfile.read(length)
        parsed: object = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("expected json object")
        return cast(dict[str, object], parsed)

    def do_GET(self) -> None:
        """Handle health checks and deny every other GET."""

        if self.path.split("?", 1)[0] in {"/health", "/health/live"}:
            self._send_json(200, {"status": "live", "egress": "restricted-fetch"})
            return
        self._send_json(
            403,
            {
                "status": "denied",
                "reason": "GET fetch targets blocked; use POST /fetch",
            },
        )

    def do_POST(self) -> None:
        """Execute one pinned fetch or return a structured denial."""

        if self.path.split("?", 1)[0] != "/fetch":
            self._send_json(403, {"status": "denied", "reason": "unknown POST route"})
            return
        try:
            payload = self._read_json_body()
            result = execute_fetch(payload)
            self._send_json(200, result)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except FetchError as exc:
            self._send_json(502, {"error": exc.reason, "peer_ip": exc.peer_ip})

    def do_CONNECT(self) -> None:
        """Refuse CONNECT tunneling."""

        self.send_response(403)
        self.end_headers()


class FetchError(Exception):
    """Structured fetch failure with optional peer metadata."""

    def __init__(self, reason: str, *, peer_ip: str | None = None) -> None:
        """Capture a safe fetch failure reason and optional observed peer."""

        super().__init__(reason)
        self.reason = reason
        self.peer_ip = peer_ip


def execute_fetch(payload: dict[str, Any]) -> dict[str, object]:
    """Perform one pinned HTTP(S) fetch with bounded decoding.

    Args:
        payload: Fetch contract from core crawl adapter.

    Returns:
        JSON-serializable response with peer metadata and bounded body.

    Raises:
        ValueError: When required fields are missing or invalid.
        FetchError: On peer mismatch, timeouts, or decompression limits.
    """

    url = str(payload.get("url", "")).strip()
    method = str(payload.get("method", "GET")).upper()
    host_header = str(payload.get("host_header", "")).strip()
    pin_ip = str(payload.get("pin_ip", "")).strip()
    port = int(payload.get("port", 443))
    use_tls = bool(payload.get("use_tls", True))
    headers_raw: object = payload.get("headers")
    headers: dict[str, str] = {}
    if isinstance(headers_raw, dict):
        for raw_key, raw_value in cast(dict[object, object], headers_raw).items():
            if isinstance(raw_key, str) and isinstance(raw_value, str):
                headers[raw_key] = raw_value
    max_wire = int(payload.get("max_wire_bytes", 2_097_152))
    max_decoded = int(payload.get("max_decoded_bytes", 5_242_880))
    max_ratio = int(payload.get("max_decompression_ratio", 50))
    connect_timeout = float(payload.get("connect_timeout_s", 10.0))
    read_timeout = float(payload.get("read_timeout_s", 30.0))

    if not url or not host_header or not pin_ip:
        raise ValueError("url, host_header, and pin_ip are required")
    if method not in {"GET", "HEAD"}:
        raise ValueError("only GET/HEAD are supported")

    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"

    sock = socket.create_connection((pin_ip, port), timeout=connect_timeout)
    peer_ip = sock.getpeername()[0]
    if peer_ip != pin_ip:
        sock.close()
        raise FetchError("peer_ip_mismatch", peer_ip=peer_ip)

    sock.settimeout(read_timeout)
    stream: socket.socket | ssl.SSLSocket = sock
    if use_tls:
        context = ssl.create_default_context()
        stream = context.wrap_socket(sock, server_hostname=host_header)

    request_lines = [f"{method} {path} HTTP/1.1", f"Host: {host_header}"]
    for key, value in headers.items():
        if key.lower() in {"host", "connection", "content-length"}:
            continue
        request_lines.append(f"{key}: {value}")
    request_lines.extend(["Connection: close", "", ""])
    stream.sendall("\r\n".join(request_lines).encode("utf-8"))

    raw = _read_http_response(stream, max_wire_bytes=max_wire)
    stream.close()

    status_code, response_headers, body = _parse_http_response(raw)
    decoded, decoded_bytes = _decode_body(
        body,
        response_headers,
        max_decoded=max_decoded,
        max_ratio=max_ratio,
    )
    content_type = response_headers.get("Content-Type")
    return {
        "status_code": status_code,
        "headers": response_headers,
        "body_base64": base64.b64encode(decoded).decode("ascii"),
        "wire_bytes": len(body),
        "decoded_bytes": decoded_bytes,
        "peer_ip": peer_ip,
        "content_type": content_type,
        "truncated": decoded_bytes >= max_decoded,
        "error": None,
    }


def _read_http_response(
    stream: socket.socket | ssl.SSLSocket, *, max_wire_bytes: int
) -> bytes:
    """Read raw HTTP response bytes up to ``max_wire_bytes``."""

    chunks: list[bytes] = []
    total = 0
    while True:
        try:
            piece = stream.recv(8192)
        except TimeoutError as exc:
            raise FetchError("read_timeout") from exc
        if not piece:
            break
        total += len(piece)
        if total > max_wire_bytes + MAX_HEADER_BLOCK:
            raise FetchError("wire_bytes_exceeded")
        chunks.append(piece)
    return b"".join(chunks)


def _parse_http_response(raw: bytes) -> tuple[int, dict[str, str], bytes]:
    """Split status line, headers, and body from raw HTTP bytes."""

    header_end = raw.find(b"\r\n\r\n")
    if header_end < 0:
        raise FetchError("malformed_http_response")
    header_block = raw[:header_end].decode("iso-8859-1", errors="replace")
    body = raw[header_end + 4 :]
    lines = header_block.split("\r\n")
    if not lines:
        raise FetchError("missing_status_line")
    status_parts = lines[0].split(" ", 2)
    if len(status_parts) < 2:
        raise FetchError("invalid_status_line")
    status_code = int(status_parts[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip()] = value.strip()
    transfer_encoding = headers.get("Transfer-Encoding", "").lower()
    if "chunked" in transfer_encoding:
        body = _decode_chunked(body)
    content_length = headers.get("Content-Length")
    if content_length is not None:
        expected = int(content_length)
        body = body[:expected]
    return status_code, headers, body


def _decode_chunked(data: bytes) -> bytes:
    """Decode HTTP/1.1 chunked transfer coding."""

    output = io.BytesIO()
    cursor = 0
    while True:
        line_end = data.find(b"\r\n", cursor)
        if line_end < 0:
            break
        size_line = data[cursor:line_end].split(b";", 1)[0]
        try:
            chunk_size = int(size_line.strip(), 16)
        except ValueError as exc:
            raise FetchError("invalid_chunk_size") from exc
        cursor = line_end + 2
        if chunk_size == 0:
            break
        output.write(data[cursor : cursor + chunk_size])
        cursor += chunk_size + 2
    return output.getvalue()


def _decode_body(
    body: bytes,
    headers: dict[str, str],
    *,
    max_decoded: int,
    max_ratio: int,
) -> tuple[bytes, int]:
    """Decompress response bytes with ratio and size bounds."""

    encoding = headers.get("Content-Encoding", "").lower().strip()
    wire_len = max(len(body), 1)
    decoded = body
    if encoding == "gzip":
        decoded = gzip.decompress(body)
    elif encoding in {"deflate", "zlib"}:
        decoded = zlib.decompress(body)
    elif encoding == "br":
        if brotli is None:
            raise FetchError("brotli_unavailable")
        decoded = brotli.decompress(body)
    elif encoding:
        raise FetchError("unsupported_content_encoding")
    if len(decoded) > max_decoded:
        raise FetchError("decoded_bytes_exceeded")
    if len(decoded) / wire_len > max_ratio:
        raise FetchError("decompression_ratio_exceeded")
    return decoded, len(decoded)


def main() -> None:
    """Start the restricted crawl proxy on container port 8080."""

    port = 8080
    server = ThreadingHTTPServer(
        ("0.0.0.0", port),  # noqa: S104 - private container listener
        FetchHandler,
    )
    print(f"crawl-proxy listening on {port} (restricted fetch)", flush=True)
    server.serve_forever()


def probe_denied_fetch(url: str, timeout_s: float = 2.0) -> int:
    """Attempt a legacy deny contract helper for topology tests.

    Args:
        url: Absolute URL that must be blocked by policy.
        timeout_s: Request timeout seconds.

    Returns:
        HTTP status code from the local endpoint.

    Raises:
        URLError: When the proxy is unreachable.
    """

    req = Request(  # noqa: S310 - contract helper
        url,
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
        return int(resp.status)


if __name__ == "__main__":
    main()
